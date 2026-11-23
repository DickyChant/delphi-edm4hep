#!/usr/bin/env python3
"""Archived evidence: locate historical bank/recalc terminal-leaf changes.

This is a leaf-level companion to ``compare_bank_recalc_untouched.py``.  The
recursive audit identifies changed top-level EDM4hep collection branches; this
script descends every such collection and hashes every terminal ROOT branch.
It therefore distinguishes the changed field(s) from bit-exact sibling fields
and cross-checks the union of changed leaf entries against the recursive audit.

Run in a Key4hep environment, for example::

  source /cvmfs/sw.hsf.org/key4hep/setup.sh -r 2026-04-08
  python3 scripts/data-reco/compare_bank_recalc_leaf_identity.py \
    --data-pairs /path/to/data_pairs.tsv \
    --mc-pairs /path/to/mc_pairs.tsv \
    --recursive-audit /path/to/bank_vs_recalc_untouched.json \
    --output /path/to/bank_vs_recalc_leaf_identity.json --workers 8

No ROOT file is modified.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import stat
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


# The prior recursive audit found exactly these top-level collections changed.
# A newly discovered top-level collection is still scanned, but because it has
# no allowlisted leaf it makes the result fail visibly.
EXPECTED_CHANGED_LEAVES = {
    "sDST_MAIN_Particles": {"sDST_MAIN_Particles.energy"},
    "sDST_SSTC_Showers": {"sDST_SSTC_Showers.iPhi"},
    "_sDST_SSTC_Showers_shapeParameters": {
        "_sDST_SSTC_Showers_shapeParameters"
    },
    "sDST_BSP_BeamSpot": {
        "sDST_BSP_BeamSpot.position.x",
        "sDST_BSP_BeamSpot.position.y",
        "sDST_BSP_BeamSpot.position.z",
    },
    "sDST_TRAC_d0BS": {"sDST_TRAC_d0BS"},
}


CPP_HELPER = r'''
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

std::string delphi_leaf_identity_sha256(TBranch* branch) {
  SHA256_CTX context;
  SHA256_Init(&context);
  const std::string identity = std::string(branch->GetName()) + '\0' +
      branch->GetClassName() + '\0' + branch->GetTitle();
  SHA256_Update(&context, identity.data(), identity.size());

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
                       (ie + 1) *
                           (basket->GetLast() - basket->GetKeylen()) / entries)
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
      SHA256_Update(&context, encoded_length, sizeof(encoded_length));
      SHA256_Update(&context, bytes + start, length);
      ++count;
    }
  }

  unsigned char encoded_count[8];
  for (int byte = 0; byte < 8; ++byte) {
    encoded_count[7 - byte] = (count >> (8 * byte)) & 0xff;
  }
  SHA256_Update(&context, encoded_count, sizeof(encoded_count));
  unsigned char digest[SHA256_DIGEST_LENGTH];
  SHA256_Final(digest, &context);
  char rendered[2 * SHA256_DIGEST_LENGTH + 1];
  for (int index = 0; index < SHA256_DIGEST_LENGTH; ++index) {
    std::sprintf(rendered + 2 * index, "%02x", digest[index]);
  }
  rendered[2 * SHA256_DIGEST_LENGTH] = '\0';
  return rendered;
}

std::vector<unsigned long long> delphi_leaf_identity_entry_hashes(
    TBranch* branch) {
  std::vector<unsigned long long> output(
      branch->GetEntries(), 1469598103934665603ULL);
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
                       (ie + 1) *
                           (basket->GetLast() - basket->GetKeylen()) / entries)
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
  return output;
}

#pragma clang diagnostic pop
'''


def regular_file(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"not a regular file: {path}")


def read_manifest(path: Path, sample: str) -> list[dict[str, Any]]:
    regular_file(path)
    result = []
    for line_number, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fields = raw.split("\t")
        if len(fields) != 2:
            raise RuntimeError(f"{path}:{line_number}: expected bank<TAB>recalc")
        bank = Path(fields[0]).resolve()
        recalc = Path(fields[1]).resolve()
        regular_file(bank)
        regular_file(recalc)
        result.append(
            {
                "sample": sample,
                "pair_index": len(result) + 1,
                "bank": str(bank),
                "recalc": str(recalc),
            }
        )
    if not result:
        raise RuntimeError(f"empty pair manifest: {path}")
    return result


def recursive_pair_index(path: Path) -> tuple[dict[tuple[str, str, str], Any], Any]:
    regular_file(path)
    document = json.loads(path.read_text())
    if document.get("format") != "delphi-bank-recalc-untouched-comparison-v1":
        raise RuntimeError(f"unrecognized recursive audit format: {path}")
    result = {}
    for pair in document.get("pairs", []):
        key = (
            pair["sample"],
            str(Path(pair["bank"]).resolve()),
            str(Path(pair["recalc"]).resolve()),
        )
        if key in result:
            raise RuntimeError(f"duplicate pair in recursive audit: {key}")
        result[key] = pair
    return result, document


def initialize_root() -> Any:
    import ROOT

    ROOT.gROOT.SetBatch(True)
    if ROOT.gSystem.Load("libcrypto") < 0:
        raise RuntimeError("could not load libcrypto")
    if not hasattr(ROOT, "delphi_leaf_identity_sha256"):
        if not ROOT.gInterpreter.Declare(CPP_HELPER):
            raise RuntimeError("could not declare ROOT leaf hash helpers")
    return ROOT


def terminal_branches(branch: Any) -> list[Any]:
    children = list(branch.GetListOfBranches())
    if not children:
        return [branch]
    result = []
    for child in children:
        result.extend(terminal_branches(child))
    return result


def branch_descriptor(branch: Any) -> dict[str, Any]:
    leaves = list(branch.GetListOfLeaves())
    return {
        "name": str(branch.GetName()),
        "class_name": str(branch.GetClassName()),
        "title": str(branch.GetTitle()),
        "leaf_types": [str(leaf.GetTypeName()) for leaf in leaves],
    }


def compare_terminal_branch(ROOT: Any, bank: Any, recalc: Any) -> dict[str, Any]:
    bank_digest = str(ROOT.delphi_leaf_identity_sha256(bank))
    recalc_digest = str(ROOT.delphi_leaf_identity_sha256(recalc))
    result = {
        "exact": bank_digest == recalc_digest,
        "bank_sha256": bank_digest,
        "recalc_sha256": recalc_digest,
    }
    if result["exact"]:
        result["changed_entries"] = {"count": 0, "first": []}
        return result

    bank_hashes = ROOT.delphi_leaf_identity_entry_hashes(bank)
    recalc_hashes = ROOT.delphi_leaf_identity_entry_hashes(recalc)
    if len(bank_hashes) != len(recalc_hashes):
        raise RuntimeError(
            f"leaf entry-count mismatch for {bank.GetName()}: "
            f"{len(bank_hashes)} != {len(recalc_hashes)}"
        )
    mismatches = [
        index
        for index, (left, right) in enumerate(zip(bank_hashes, recalc_hashes))
        if left != right
    ]
    if not mismatches:
        raise RuntimeError(
            f"SHA-256 differs but entry hashes do not for {bank.GetName()}"
        )
    result["changed_entries"] = {
        "count": len(mismatches),
        "first": mismatches[:5],
    }
    result["_changed_entry_indices"] = mismatches
    return result


def process_pair(row: dict[str, Any]) -> dict[str, Any]:
    ROOT = initialize_root()
    bank_file = ROOT.TFile.Open(row["bank"], "READ")
    recalc_file = ROOT.TFile.Open(row["recalc"], "READ")
    if not bank_file or bank_file.IsZombie():
        raise RuntimeError(f"cannot open bank file: {row['bank']}")
    if not recalc_file or recalc_file.IsZombie():
        raise RuntimeError(f"cannot open recalc file: {row['recalc']}")
    bank_tree = bank_file.Get("events")
    recalc_tree = recalc_file.Get("events")
    if not bank_tree or not recalc_tree:
        raise RuntimeError("missing events tree")
    entries = int(bank_tree.GetEntries())
    if entries != int(recalc_tree.GetEntries()) or entries != row["entries"]:
        raise RuntimeError(
            f"event count mismatch for {row['bank']}: "
            f"{entries}, {int(recalc_tree.GetEntries())}, {row['entries']}"
        )

    top_results = {}
    for top_name in row["target_top_levels"]:
        bank_top = bank_tree.GetBranch(top_name)
        recalc_top = recalc_tree.GetBranch(top_name)
        if not bank_top or not recalc_top:
            raise RuntimeError(f"missing target top-level branch: {top_name}")
        bank_leaves = {
            str(branch.GetName()): branch for branch in terminal_branches(bank_top)
        }
        recalc_leaves = {
            str(branch.GetName()): branch
            for branch in terminal_branches(recalc_top)
        }
        bank_schema = {
            name: branch_descriptor(branch)
            for name, branch in sorted(bank_leaves.items())
        }
        recalc_schema = {
            name: branch_descriptor(branch)
            for name, branch in sorted(recalc_leaves.items())
        }
        schema_exact = bank_schema == recalc_schema
        if not schema_exact:
            top_results[top_name] = {
                "schema_exact": False,
                "bank_terminal_schema": bank_schema,
                "recalc_terminal_schema": recalc_schema,
                "recursive_changed_entries": row["recursive_changed"].get(
                    top_name, 0
                ),
            }
            continue

        leaf_results = {}
        union = set()
        for leaf_name in sorted(bank_leaves):
            leaf_result = compare_terminal_branch(
                ROOT, bank_leaves[leaf_name], recalc_leaves[leaf_name]
            )
            union.update(leaf_result.pop("_changed_entry_indices", []))
            leaf_results[leaf_name] = leaf_result
        recursive_count = row["recursive_changed"].get(top_name, 0)
        top_results[top_name] = {
            "schema_exact": True,
            "terminal_schema": list(bank_schema.values()),
            "terminal_leaf_count": len(bank_leaves),
            "changed_leaf_union_entries": {
                "count": len(union),
                "first": sorted(union)[:5],
            },
            "recursive_changed_entries": recursive_count,
            "matches_recursive_audit": len(union) == recursive_count,
            "leaf_results": leaf_results,
        }

    bank_file.Close()
    recalc_file.Close()
    return {
        "sample": row["sample"],
        "pair_index": row["pair_index"],
        "bank": row["bank"],
        "recalc": row["recalc"],
        "entries": entries,
        "top_levels": top_results,
    }


def summarize_sample(results: list[dict[str, Any]]) -> dict[str, Any]:
    leaf_pair_counts: Counter[str] = Counter()
    leaf_entry_counts: Counter[str] = Counter()
    unexpected_pair_counts: Counter[str] = Counter()
    recursive_top_pair_counts: Counter[str] = Counter()
    recursive_top_entry_counts: Counter[str] = Counter()
    reconstructed_top_pair_counts: Counter[str] = Counter()
    reconstructed_top_entry_counts: Counter[str] = Counter()
    top_leaf_schemas: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    top_pairs_scanned: Counter[str] = Counter()
    schema_failures = 0
    recursive_crosscheck_failures = 0

    for pair in results:
        for top_name, top in pair["top_levels"].items():
            top_pairs_scanned[top_name] += 1
            if not top["schema_exact"]:
                schema_failures += 1
                continue
            schema = {item["name"]: item for item in top["terminal_schema"]}
            if top_leaf_schemas[top_name] and top_leaf_schemas[top_name] != schema:
                schema_failures += 1
            elif not top_leaf_schemas[top_name]:
                top_leaf_schemas[top_name] = schema
            recursive_count = top["recursive_changed_entries"]
            reconstructed_count = top["changed_leaf_union_entries"]["count"]
            if recursive_count:
                recursive_top_pair_counts[top_name] += 1
                recursive_top_entry_counts[top_name] += recursive_count
            if reconstructed_count:
                reconstructed_top_pair_counts[top_name] += 1
                reconstructed_top_entry_counts[top_name] += reconstructed_count
            if not top["matches_recursive_audit"]:
                recursive_crosscheck_failures += 1
            expected = EXPECTED_CHANGED_LEAVES.get(top_name, set())
            for leaf_name, leaf in top["leaf_results"].items():
                count = leaf["changed_entries"]["count"]
                if not count:
                    continue
                leaf_pair_counts[leaf_name] += 1
                leaf_entry_counts[leaf_name] += count
                if leaf_name not in expected:
                    unexpected_pair_counts[leaf_name] += 1

    top_summaries = {}
    for top_name in sorted(top_pairs_scanned):
        schema = top_leaf_schemas[top_name]
        changed = {
            name: {
                "pairs_with_changes": leaf_pair_counts[name],
                "changed_entry_occurrences": leaf_entry_counts[name],
            }
            for name in sorted(schema)
            if leaf_pair_counts[name]
        }
        exact_siblings = sorted(
            name for name in schema if leaf_pair_counts[name] == 0
        )
        top_summaries[top_name] = {
            "pairs_scanned": top_pairs_scanned[top_name],
            "terminal_leaf_count": len(schema),
            "terminal_schema": list(schema.values()),
            "expected_changed_leaves": sorted(
                EXPECTED_CHANGED_LEAVES.get(top_name, set())
            ),
            "changed_leaves": changed,
            "exact_sibling_leaves_across_all_pairs": exact_siblings,
            "recursive_changed_pairs": recursive_top_pair_counts[top_name],
            "recursive_changed_entry_occurrences": recursive_top_entry_counts[
                top_name
            ],
            "leaf_union_changed_pairs": reconstructed_top_pair_counts[top_name],
            "leaf_union_changed_entry_occurrences": reconstructed_top_entry_counts[
                top_name
            ],
        }

    return {
        "pairs": len(results),
        "events": sum(pair["entries"] for pair in results),
        "schema_failures": schema_failures,
        "recursive_crosscheck_failures": recursive_crosscheck_failures,
        "unexpected_changed_leaf_pair_counts": dict(
            sorted(unexpected_pair_counts.items())
        ),
        "top_levels": top_summaries,
    }


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-pairs", type=Path, required=True)
    parser.add_argument("--mc-pairs", type=Path, required=True)
    parser.add_argument("--recursive-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--limit-per-sample",
        type=int,
        help="development aid: scan only the first N pairs of each sample",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    if args.limit_per_sample is not None and args.limit_per_sample < 1:
        raise SystemExit("--limit-per-sample must be positive")

    rows = read_manifest(args.data_pairs, "data") + read_manifest(
        args.mc_pairs, "mc"
    )
    recursive_index, recursive_document = recursive_pair_index(
        args.recursive_audit
    )
    manifest_keys = {
        (row["sample"], row["bank"], row["recalc"]) for row in rows
    }
    if manifest_keys != set(recursive_index):
        missing = sorted(manifest_keys - set(recursive_index))
        extra = sorted(set(recursive_index) - manifest_keys)
        raise RuntimeError(
            "manifest/recursive-audit pair mismatch: "
            f"missing_from_audit={missing[:3]} extra_in_audit={extra[:3]}"
        )

    target_top_levels = defaultdict(set)
    for key, recursive_pair in recursive_index.items():
        target_top_levels[key[0]].update(
            recursive_pair["common_collection_branches"]["changed_entries"]
        )
    expected_target_union = set(EXPECTED_CHANGED_LEAVES)
    observed_target_union = set().union(*target_top_levels.values())
    missing_targets = sorted(expected_target_union - observed_target_union)
    unexpected_targets = sorted(observed_target_union - expected_target_union)

    selected_rows = []
    selected_by_sample: Counter[str] = Counter()
    for row in rows:
        if (
            args.limit_per_sample is not None
            and selected_by_sample[row["sample"]] >= args.limit_per_sample
        ):
            continue
        key = (row["sample"], row["bank"], row["recalc"])
        recursive_pair = recursive_index[key]
        row["entries"] = int(recursive_pair["entries"])
        row["recursive_changed"] = {
            name: int(detail["count"])
            for name, detail in recursive_pair["common_collection_branches"][
                "changed_entries"
            ].items()
        }
        row["target_top_levels"] = sorted(target_top_levels[row["sample"]])
        selected_rows.append(row)
        selected_by_sample[row["sample"]] += 1

    results = []
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, max_tasks_per_child=1
    ) as pool:
        futures = {pool.submit(process_pair, row): row for row in selected_rows}
        for completed, future in enumerate(
            concurrent.futures.as_completed(futures), 1
        ):
            result = future.result()
            results.append(result)
            changed = []
            unexpected = []
            recursive_ok = True
            for top_name, top in result["top_levels"].items():
                if not top["schema_exact"]:
                    recursive_ok = False
                    continue
                recursive_ok &= top["matches_recursive_audit"]
                expected = EXPECTED_CHANGED_LEAVES.get(top_name, set())
                for leaf_name, leaf in top["leaf_results"].items():
                    if leaf["changed_entries"]["count"]:
                        changed.append(leaf_name)
                        if leaf_name not in expected:
                            unexpected.append(leaf_name)
            if unexpected:
                print(
                    "UNEXPECTED_CHANGED_LEAF "
                    f"sample={result['sample']} bank={result['bank']} "
                    f"leaves={','.join(sorted(unexpected))}",
                    flush=True,
                )
            print(
                f"[{completed}/{len(selected_rows)}] {result['sample']} "
                f"{Path(result['bank']).name} entries={result['entries']} "
                f"changed_leaves={len(changed)} unexpected={len(unexpected)} "
                f"recursive_ok={recursive_ok}",
                flush=True,
            )

    results.sort(key=lambda item: (item["sample"], item["pair_index"]))
    samples = {
        sample: summarize_sample(
            [result for result in results if result["sample"] == sample]
        )
        for sample in ("data", "mc")
    }
    complete = args.limit_per_sample is None
    passed = (
        not unexpected_targets
        and all(
            sample["schema_failures"] == 0
            and sample["recursive_crosscheck_failures"] == 0
            and not sample["unexpected_changed_leaf_pair_counts"]
            for sample in samples.values()
        )
    )
    script_path = Path(__file__).resolve()
    payload = {
        "format": "delphi-bank-recalc-leaf-identity-v1",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "complete": complete,
        "semantics": {
            "leaf_comparison": (
                "SHA-256 of branch identity plus ordered uncompressed per-event "
                "terminal ROOT-branch payload; independent of basket boundaries "
                "and compression"
            ),
            "event_count_comparison": (
                "64-bit FNV-1a of each uncompressed terminal-branch event payload"
            ),
            "scope": (
                "all terminal descendants of every common top-level collection "
                "reported changed by the recursive audit"
            ),
        },
        "inputs": {
            "data_pairs": str(args.data_pairs.resolve()),
            "mc_pairs": str(args.mc_pairs.resolve()),
            "recursive_audit": str(args.recursive_audit.resolve()),
            "recursive_audit_generated_utc": recursive_document.get(
                "generated_utc"
            ),
            "workers": args.workers,
            "limit_per_sample": args.limit_per_sample,
        },
        "script": str(script_path),
        "script_sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
        "expected_changed_leaves": {
            name: sorted(leaves)
            for name, leaves in sorted(EXPECTED_CHANGED_LEAVES.items())
        },
        "observed_changed_top_levels": {
            sample: sorted(names) for sample, names in sorted(target_top_levels.items())
        },
        "expected_top_levels_not_seen": missing_targets,
        "unexpected_changed_top_levels": unexpected_targets,
        "samples": samples,
        "pairs": results,
    }
    atomic_json(args.output.resolve(), payload)
    print(
        f"status={payload['status']} complete={complete} "
        f"output={args.output.resolve()}",
        flush=True,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
