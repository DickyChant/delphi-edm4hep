#!/usr/bin/env python3
"""Archived evidence: audit historical bank/recalc non-btag changes.

The two productions are independent ROOT files, so file checksums and basket
boundaries are not meaningful equality tests.  This audit hashes each
uncompressed, per-event branch payload and compares frame parameters by name.
Only the BTG/AABTAG payload and the two BTAGCFG steering parameters are
excluded from the untouched-parameter comparison.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import os
import stat
import tempfile
from collections import Counter
from pathlib import Path


GP_BRANCHES = {
    f"GP{kind}{suffix}"
    for kind in ("Int", "Float", "Double", "String")
    for suffix in ("Keys", "Values")
}

EXPECTED_RECALC_ONLY_BRANCHES = {
    "sDST_AABTAG_PrimaryVertex",
    "_sDST_AABTAG_PrimaryVertex_particles",
    "_sDST_AABTAG_PrimaryVertex_parameters",
    "sDST_AABTAG_Tracks_AttachedToPV",
    "sDST_AABTAG_Tracks_Chi2PV",
    "sDST_AABTAG_Tracks_Chi2VD",
    "sDST_AABTAG_Tracks_ImpactParRPhi",
    "sDST_AABTAG_Tracks_ImpactParRPhiError",
    "sDST_AABTAG_Tracks_ImpactParZ",
    "sDST_AABTAG_Tracks_ImpactParZError",
    "sDST_AABTAG_Tracks_Momentum",
    "sDST_AABTAG_Tracks_NVDHitsRPhi",
    "sDST_AABTAG_Tracks_NVDHitsZ",
    "sDST_AABTAG_Tracks_NVDLayersRPhi",
    "sDST_AABTAG_Tracks_NVDLayersZ",
    "sDST_AABTAG_Tracks_ParticleIndex",
    "sDST_AABTAG_Tracks_ProbRPhi",
    "sDST_AABTAG_Tracks_ProbZ",
    "sDST_AABTAG_Tracks_UsedForTag",
}

# These campaigns use BtagPrimaryVertex::Keep (IFLPVT=0), so the DELANA PV and
# its PV-relative impact quantities remain in the strict untouched set.  On
# MC, IFLBTG=2 redraws SKELANA's artificial beamspot and consequently changes
# the beamspot-relative d0 values.  Report only that known coupling separately;
# everything else must remain byte-exact at the serialized per-event level.
AABTAG_COUPLED_COMMON_BRANCHES = {
    "sDST_BSP_BeamSpot",
    "sDST_TRAC_d0BS",
}

EXPECTED_PARAMETER_NAMES = {
    "sDST_BTAGCFG_Mode",
    "sDST_BTAGCFG_Recalculated",
}

# On simulation, IFLBTG=2 deliberately draws the artificial reconstruction
# beamspot around the true interaction point.  The corresponding d0BS branch
# is listed in AABTAG_COUPLED_COMMON_BRANCHES above.  Keep these parameters in
# the comparison, but report them as coupled changes rather than silently
# excluding them or calling them unrelated corruption.
AABTAG_COUPLED_PARAMETER_NAMES = {
    "sDST_EVT_BeamSpotX",
    "sDST_EVT_BeamSpotY",
    "sDST_EVT_BeamSpotZ",
}


def is_btag_parameter(name: str) -> bool:
    return (
        name.startswith("sDST_BTG_")
        or name.startswith("sDST_AABTAG_")
        or name in EXPECTED_PARAMETER_NAMES
    )


def regular_file(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"not a regular file: {path}")


def read_manifest(path: Path, label: str) -> list[tuple[str, str, str]]:
    regular_file(path)
    rows = []
    for line_number, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fields = raw.split("\t")
        if len(fields) != 2:
            raise RuntimeError(f"{path}:{line_number}: expected two tab fields")
        bank = Path(fields[0])
        recalc = Path(fields[1])
        regular_file(bank)
        regular_file(recalc)
        rows.append((label, str(bank.resolve()), str(recalc.resolve())))
    if not rows:
        raise RuntimeError(f"empty pair manifest: {path}")
    return rows


def initialize_root():
    import ROOT

    ROOT.gROOT.SetBatch(True)
    if ROOT.gSystem.Load("libcrypto") < 0:
        raise RuntimeError("could not load libcrypto")
    if not hasattr(ROOT, "delphi_untouched_branch_sha256"):
        declared = ROOT.gInterpreter.Declare(
            r'''
#include <openssl/sha.h>
#include <TBasket.h>
#include <TBranch.h>
#include <TBuffer.h>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"

void delphi_untouched_hash_branch(TBranch* branch, SHA256_CTX* context) {
  const std::string identity = std::string(branch->GetName()) + '\0' +
      branch->GetClassName() + '\0' + branch->GetTitle();
  SHA256_Update(context, identity.data(), identity.size());
  unsigned long long count = 0;
  auto* basket_bytes = branch->GetBasketBytes();
  for (int ib = 0; basket_bytes && ib < branch->GetMaxBaskets(); ++ib) {
    if (basket_bytes[ib] <= 0) continue;
    auto* basket = branch->GetBasket(ib);
    if (!basket) throw std::runtime_error("cannot read ROOT basket");
    auto* offsets = basket->GetEntryOffset();
    auto* buffer = basket->GetBufferRef();
    const auto* bytes =
        reinterpret_cast<const unsigned char*>(buffer->Buffer());
    const int entries = basket->GetNevBuf();
    for (int ie = 0; ie < entries; ++ie) {
      const int start = offsets
          ? offsets[ie]
          : basket->GetKeylen() +
                ie * (basket->GetLast() - basket->GetKeylen()) / entries;
      const int end = (ie + 1 < entries)
          ? (offsets
                 ? offsets[ie + 1]
                 : basket->GetKeylen() +
                       (ie + 1) * (basket->GetLast() - basket->GetKeylen()) /
                           entries)
          : basket->GetLast();
      if (start < basket->GetKeylen() || end < start ||
          end > basket->GetLast()) {
        throw std::runtime_error("invalid ROOT basket entry offsets");
      }
      const unsigned long long length = end - start;
      unsigned char encoded_length[8];
      for (int byte = 0; byte < 8; ++byte) {
        encoded_length[7 - byte] = (length >> (8 * byte)) & 0xff;
      }
      SHA256_Update(context, encoded_length, sizeof(encoded_length));
      SHA256_Update(context, bytes + start, length);
      ++count;
    }
  }
  unsigned char encoded_count[8];
  for (int byte = 0; byte < 8; ++byte) {
    encoded_count[7 - byte] = (count >> (8 * byte)) & 0xff;
  }
  SHA256_Update(context, encoded_count, sizeof(encoded_count));
  for (auto* object : *branch->GetListOfBranches()) {
    delphi_untouched_hash_branch(static_cast<TBranch*>(object), context);
  }
}

std::string delphi_untouched_branch_sha256(TBranch* branch) {
  SHA256_CTX context;
  SHA256_Init(&context);
  delphi_untouched_hash_branch(branch, &context);
  unsigned char digest[SHA256_DIGEST_LENGTH];
  SHA256_Final(digest, &context);
  char rendered[2 * SHA256_DIGEST_LENGTH + 1];
  for (int index = 0; index < SHA256_DIGEST_LENGTH; ++index) {
    std::sprintf(rendered + 2 * index, "%02x", digest[index]);
  }
  rendered[2 * SHA256_DIGEST_LENGTH] = '\0';
  return rendered;
}

void delphi_untouched_update_entry_hashes(
    TBranch* branch, std::vector<unsigned long long>& output) {
  auto* basket_bytes = branch->GetBasketBytes();
  auto* basket_entries = branch->GetBasketEntry();
  for (int ib = 0; basket_bytes && ib < branch->GetMaxBaskets(); ++ib) {
    if (basket_bytes[ib] <= 0) continue;
    auto* basket = branch->GetBasket(ib);
    if (!basket) throw std::runtime_error("cannot read ROOT basket");
    auto* offsets = basket->GetEntryOffset();
    auto* buffer = basket->GetBufferRef();
    const auto* bytes =
        reinterpret_cast<const unsigned char*>(buffer->Buffer());
    const int entries = basket->GetNevBuf();
    for (int ie = 0; ie < entries; ++ie) {
      const int start = offsets
          ? offsets[ie]
          : basket->GetKeylen() +
                ie * (basket->GetLast() - basket->GetKeylen()) / entries;
      const int end = (ie + 1 < entries)
          ? (offsets
                 ? offsets[ie + 1]
                 : basket->GetKeylen() +
                       (ie + 1) * (basket->GetLast() - basket->GetKeylen()) /
                           entries)
          : basket->GetLast();
      auto& hash = output[basket_entries[ib] + ie];
      for (int index = start; index < end; ++index) {
        hash ^= bytes[index];
        hash *= 1099511628211ULL;
      }
      hash ^= static_cast<unsigned long long>(end - start);
      hash *= 1099511628211ULL;
    }
  }
  for (auto* object : *branch->GetListOfBranches()) {
    delphi_untouched_update_entry_hashes(
        static_cast<TBranch*>(object), output);
  }
}

std::vector<unsigned long long> delphi_untouched_entry_hashes(
    TBranch* branch) {
  std::vector<unsigned long long> output(
      branch->GetEntries(), 1469598103934665603ULL);
  delphi_untouched_update_entry_hashes(branch, output);
  return output;
}

#pragma clang diagnostic pop
'''
        )
        if not declared:
            raise RuntimeError("could not declare ROOT branch hash helpers")
    return ROOT


def normalized_value(kind: str, value):
    if kind == "String":
        return tuple(bytes(item).decode("utf-8", "surrogateescape") for item in value)
    return tuple(value)


def same_parameter_value(kind: str, left, right) -> bool:
    if len(left) != len(right):
        return False
    if kind not in ("Float", "Double"):
        return left == right
    return all(
        a == b or (math.isnan(float(a)) and math.isnan(float(b)))
        for a, b in zip(left, right)
    )


def parameter_maps(tree, kinds):
    maps = {}
    for kind in kinds:
        keys = getattr(tree, f"GP{kind}Keys")
        values = getattr(tree, f"GP{kind}Values")
        if len(keys) != len(values):
            raise RuntimeError(f"GP{kind} key/value length mismatch")
        current = {}
        for key, value in zip(keys, values):
            name = str(key)
            if name in current:
                raise RuntimeError(f"duplicate frame parameter {name!r}")
            current[name] = normalized_value(kind, value)
        maps[kind] = current
    return maps


def compare_parameters(left, right, max_examples=5):
    kinds = ("Int", "Float", "Double", "String")
    for tree in (left, right):
        tree.SetBranchStatus("*", 0)
        for kind in kinds:
            tree.SetBranchStatus(f"GP{kind}Keys", 1)
            tree.SetBranchStatus(f"GP{kind}Values", 1)

    mismatch_entries = 0
    mismatch_fields = Counter()
    coupled_mismatch_entries = 0
    coupled_mismatch_fields = Counter()
    examples = []
    config_failures = 0
    for entry in range(left.GetEntries()):
        left.GetEntry(entry)
        right.GetEntry(entry)
        left_maps = parameter_maps(left, kinds)
        right_maps = parameter_maps(right, kinds)

        left_mode = left_maps["String"].get("sDST_BTAGCFG_Mode")
        right_mode = right_maps["String"].get("sDST_BTAGCFG_Mode")
        left_recalc = left_maps["Int"].get("sDST_BTAGCFG_Recalculated")
        right_recalc = right_maps["Int"].get("sDST_BTAGCFG_Recalculated")
        if not (
            left_mode == ("bank",)
            and right_mode == ("recalc",)
            and left_recalc == (0,)
            and right_recalc == (1,)
        ):
            config_failures += 1

        entry_fields = []
        coupled_entry_fields = []
        for kind in kinds:
            left_clean = {
                key: value
                for key, value in left_maps[kind].items()
                if not is_btag_parameter(key)
            }
            right_clean = {
                key: value
                for key, value in right_maps[kind].items()
                if not is_btag_parameter(key)
            }
            for key in sorted(set(left_clean) | set(right_clean)):
                if key not in left_clean or key not in right_clean or not same_parameter_value(
                    kind, left_clean.get(key, ()), right_clean.get(key, ())
                ):
                    field = f"{kind}:{key}"
                    if key in AABTAG_COUPLED_PARAMETER_NAMES:
                        coupled_mismatch_fields[field] += 1
                        coupled_entry_fields.append(field)
                    else:
                        mismatch_fields[field] += 1
                        entry_fields.append(field)
        if coupled_entry_fields:
            coupled_mismatch_entries += 1
        if entry_fields:
            mismatch_entries += 1
            if len(examples) < max_examples:
                examples.append({"entry": entry, "fields": entry_fields[:20]})

    for tree in (left, right):
        tree.SetBranchStatus("*", 1)
    return {
        "entries_compared": int(left.GetEntries()),
        "unexpected_mismatch_entries": mismatch_entries,
        "unexpected_mismatch_fields": dict(sorted(mismatch_fields.items())),
        "first_unexpected_mismatches": examples,
        "aabtag_coupled_mismatch_entries": coupled_mismatch_entries,
        "aabtag_coupled_mismatch_fields": dict(
            sorted(coupled_mismatch_fields.items())
        ),
        "expected_btagcfg_contract_failure_entries": config_failures,
    }


def process_pair(row):
    label, bank_path, recalc_path = row
    ROOT = initialize_root()
    bank_file = ROOT.TFile.Open(bank_path, "READ")
    recalc_file = ROOT.TFile.Open(recalc_path, "READ")
    if not bank_file or bank_file.IsZombie():
        raise RuntimeError(f"cannot open {bank_path}")
    if not recalc_file or recalc_file.IsZombie():
        raise RuntimeError(f"cannot open {recalc_path}")
    bank = bank_file.Get("events")
    recalc = recalc_file.Get("events")
    if not bank or not recalc:
        raise RuntimeError("missing events tree")
    if bank.GetEntries() != recalc.GetEntries():
        raise RuntimeError(
            f"event-count mismatch: {bank.GetEntries()} vs {recalc.GetEntries()}"
        )

    bank_branches = {branch.GetName(): branch for branch in bank.GetListOfBranches()}
    recalc_branches = {
        branch.GetName(): branch for branch in recalc.GetListOfBranches()
    }
    bank_only = sorted(set(bank_branches) - set(recalc_branches))
    recalc_only = sorted(set(recalc_branches) - set(bank_branches))
    common = sorted(set(bank_branches) & set(recalc_branches) - GP_BRANCHES)

    changed = []
    changed_entries = {}
    for name in common:
        left_digest = str(ROOT.delphi_untouched_branch_sha256(bank_branches[name]))
        right_digest = str(ROOT.delphi_untouched_branch_sha256(recalc_branches[name]))
        if left_digest != right_digest:
            changed.append(name)
            left_hashes = ROOT.delphi_untouched_entry_hashes(bank_branches[name])
            right_hashes = ROOT.delphi_untouched_entry_hashes(recalc_branches[name])
            differences = [
                index
                for index, (left_hash, right_hash) in enumerate(
                    zip(left_hashes, right_hashes)
                )
                if left_hash != right_hash
            ]
            changed_entries[name] = {
                "count": len(differences),
                "first": differences[:5],
            }

    parameters = compare_parameters(bank, recalc)
    bank_file.Close()
    recalc_file.Close()
    coupled = sorted(set(changed) & AABTAG_COUPLED_COMMON_BRANCHES)
    unexpected = sorted(set(changed) - AABTAG_COUPLED_COMMON_BRANCHES)
    return {
        "sample": label,
        "bank": bank_path,
        "recalc": recalc_path,
        "entries": int(parameters["entries_compared"]),
        "schema": {
            "bank_only": bank_only,
            "recalc_only": recalc_only,
            "recalc_only_is_exact_aabtag_schema": set(recalc_only)
            == EXPECTED_RECALC_ONLY_BRANCHES,
        },
        "common_collection_branches": {
            "checked": len(common),
            "exact": len(common) - len(changed),
            "changed_aabtag_coupled": coupled,
            "changed_unexpected_untouched": unexpected,
            "changed_entries": changed_entries,
        },
        "parameters": parameters,
    }


def atomic_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-pairs", type=Path, required=True)
    parser.add_argument("--mc-pairs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")

    rows = read_manifest(args.data_pairs, "data") + read_manifest(
        args.mc_pairs, "mc"
    )
    if args.limit is not None:
        if args.limit < 1:
            parser.error("--limit must be positive")
        rows = rows[: args.limit]

    results = []
    # ROOT keeps branch/basket objects in process-global registries.  Reusing a
    # Python worker after closing the files can leave stale interpreter-side
    # proxies, so make each pair audit process-isolated.
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, max_tasks_per_child=1
    ) as pool:
        futures = {pool.submit(process_pair, row): row for row in rows}
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            result = future.result()
            results.append(result)
            print(
                f"[{completed}/{len(rows)}] {result['sample']} "
                f"{Path(result['bank']).name} entries={result['entries']} "
                f"unexpected_branches="
                f"{len(result['common_collection_branches']['changed_unexpected_untouched'])} "
                f"parameter_mismatch_entries="
                f"{result['parameters']['unexpected_mismatch_entries']}",
                flush=True,
            )

    results.sort(key=lambda item: (item["sample"], item["bank"]))
    samples = {}
    for label in ("data", "mc"):
        selected = [item for item in results if item["sample"] == label]
        branch_pair_counts = Counter()
        branch_entry_counts = Counter()
        unexpected_parameter_fields = Counter()
        coupled_parameter_fields = Counter()
        for item in selected:
            common = item["common_collection_branches"]
            for name in common["changed_aabtag_coupled"] + common[
                "changed_unexpected_untouched"
            ]:
                branch_pair_counts[name] += 1
                branch_entry_counts[name] += common["changed_entries"][name]["count"]
            unexpected_parameter_fields.update(
                item["parameters"]["unexpected_mismatch_fields"]
            )
            coupled_parameter_fields.update(
                item["parameters"]["aabtag_coupled_mismatch_fields"]
            )
        samples[label] = {
            "pairs": len(selected),
            "events": sum(item["entries"] for item in selected),
            "schema_failures": sum(
                bool(item["schema"]["bank_only"])
                or not item["schema"]["recalc_only_is_exact_aabtag_schema"]
                for item in selected
            ),
            "aabtag_coupled_changed_pair_counts": {
                name: branch_pair_counts[name]
                for name in sorted(AABTAG_COUPLED_COMMON_BRANCHES)
                if branch_pair_counts[name]
            },
            "aabtag_coupled_changed_entry_counts": {
                name: branch_entry_counts[name]
                for name in sorted(AABTAG_COUPLED_COMMON_BRANCHES)
                if branch_entry_counts[name]
            },
            "unexpected_untouched_changed_pair_counts": {
                name: count
                for name, count in sorted(branch_pair_counts.items())
                if name not in AABTAG_COUPLED_COMMON_BRANCHES
            },
            "unexpected_untouched_changed_entry_counts": {
                name: count
                for name, count in sorted(branch_entry_counts.items())
                if name not in AABTAG_COUPLED_COMMON_BRANCHES
            },
            "unexpected_parameter_mismatch_entries": sum(
                item["parameters"]["unexpected_mismatch_entries"]
                for item in selected
            ),
            "unexpected_parameter_fields": dict(
                sorted(unexpected_parameter_fields.items())
            ),
            "aabtag_coupled_parameter_mismatch_entries": sum(
                item["parameters"]["aabtag_coupled_mismatch_entries"]
                for item in selected
            ),
            "aabtag_coupled_parameter_fields": dict(
                sorted(coupled_parameter_fields.items())
            ),
            "btagcfg_contract_failure_entries": sum(
                item["parameters"]["expected_btagcfg_contract_failure_entries"]
                for item in selected
            ),
        }

    strict_pass = all(
        sample["schema_failures"] == 0
        and not sample["unexpected_untouched_changed_pair_counts"]
        and sample["unexpected_parameter_mismatch_entries"] == 0
        and sample["btagcfg_contract_failure_entries"] == 0
        for sample in samples.values()
    )
    payload = {
        "format": "delphi-bank-recalc-untouched-comparison-v1",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if strict_pass else "FAIL",
        "semantics": {
            "collection_comparison": (
                "SHA-256 of ordered uncompressed per-event ROOT payloads; "
                "independent of basket boundaries and compression"
            ),
            "common_primary_vertex_contract": (
                "BtagPrimaryVertex::Keep (IFLPVT=0); DELANA PV and PV-relative "
                "impact quantities are strict untouched fields"
            ),
            "parameter_comparison": (
                "exact by parameter name and ordered value, paired NaN equal"
            ),
            "expected_parameter_exclusions": [
                "sDST_BTG_*",
                "sDST_AABTAG_*",
                "sDST_BTAGCFG_Mode",
                "sDST_BTAGCFG_Recalculated",
            ],
            "aabtag_coupled_common_branches": sorted(
                AABTAG_COUPLED_COMMON_BRANCHES
            ),
            "aabtag_coupled_parameters": sorted(
                AABTAG_COUPLED_PARAMETER_NAMES
            ),
        },
        "inputs": {
            "data_pairs": str(args.data_pairs.resolve()),
            "mc_pairs": str(args.mc_pairs.resolve()),
            "workers": args.workers,
            "limit": args.limit,
        },
        "samples": samples,
        "pairs": results,
    }
    atomic_json(args.output.resolve(), payload)
    print(f"status={payload['status']} output={args.output.resolve()}")
    return 0 if strict_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
