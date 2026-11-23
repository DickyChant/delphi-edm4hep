#!/usr/bin/env python3
"""Archived evidence: quantify historical bank/recalc float differences.

This is a deliberately narrow companion to compare_bank_recalc_untouched.py.  It
does not decide whether a branch is allowed to change.  Instead, it reads only
the explicitly selected float fields and reports bit differences, numerical
magnitudes, and ULP distances for already aligned bank/recalc file pairs.

Run in a Key4hep environment, for example:

  source /cvmfs/sw.hsf.org/key4hep/setup.sh -r 2026-04-08
  python3 scripts/data-reco/compare_bank_recalc_float_deltas.py \
    --data-pairs /path/to/data_pairs.tsv --mc-pairs /path/to/mc_pairs.tsv \
    --output float_deltas.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_LEAF_FIELDS = (
    "sDST_MAIN_Particles.energy",
    "sDST_SSTC_Showers.iPhi",
)
DATA_VECTOR_FIELDS = ("_sDST_SSTC_Showers_shapeParameters",)

MC_LEAF_FIELDS = (
    "sDST_MAIN_Particles.energy",
    "sDST_SSTC_Showers.iPhi",
    "sDST_BSP_BeamSpot.position.x",
    "sDST_BSP_BeamSpot.position.y",
    "sDST_BSP_BeamSpot.position.z",
)
MC_VECTOR_FIELDS = (
    "_sDST_SSTC_Showers_shapeParameters",
    "sDST_TRAC_d0BS",
)


CPP_HELPER = r"""
#include <TFile.h>
#include <TTree.h>
#include <TTreeReader.h>
#include <TTreeReaderArray.h>
#include <TTreeReaderValue.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace BankRecalcFloatDelta {

struct Example {
  long long entry = -1;
  unsigned long long index = 0;
  float bank = 0.0f;
  float recalc = 0.0f;
  double delta = 0.0;
  unsigned long long ulp = 0;
  unsigned int bank_bits = 0;
  unsigned int recalc_bits = 0;
};

struct Summary {
  std::string field;
  std::string storage;
  long long entries = 0;
  long long differing_entries = 0;
  long long length_mismatch_entries = 0;
  unsigned long long bank_observations = 0;
  unsigned long long recalc_observations = 0;
  unsigned long long compared_observations = 0;
  unsigned long long differing_observations = 0;
  unsigned long long nonfinite_differences = 0;
  double min_delta = std::numeric_limits<double>::infinity();
  double max_delta = -std::numeric_limits<double>::infinity();
  double max_abs_delta = -1.0;
  unsigned long long max_ulp = 0;
  Example max_abs_example;
  Example max_ulp_example;
  std::vector<Example> examples;
};

inline std::uint32_t floatBits(float value) {
  std::uint32_t bits = 0;
  std::memcpy(&bits, &value, sizeof(bits));
  return bits;
}

inline std::uint32_t orderedBits(std::uint32_t bits) {
  // Adjacent representable floats map to adjacent unsigned integers across
  // negative values and across signed zero.
  return (bits & 0x80000000u) ? ~bits : (bits | 0x80000000u);
}

inline std::uint64_t ulpDistance(float lhs, float rhs) {
  const auto a = orderedBits(floatBits(lhs));
  const auto b = orderedBits(floatBits(rhs));
  return a >= b ? static_cast<std::uint64_t>(a - b)
                : static_cast<std::uint64_t>(b - a);
}

inline Example makeExample(long long entry, std::size_t index, float bank,
                           float recalc) {
  Example result;
  result.entry = entry;
  result.index = index;
  result.bank = bank;
  result.recalc = recalc;
  result.delta = static_cast<double>(recalc) - static_cast<double>(bank);
  result.ulp = ulpDistance(bank, recalc);
  result.bank_bits = floatBits(bank);
  result.recalc_bits = floatBits(recalc);
  return result;
}

inline void compareValues(Summary& result, long long entry,
                          const float* bank, std::size_t bank_size,
                          const float* recalc, std::size_t recalc_size,
                          std::size_t max_examples) {
  ++result.entries;
  result.bank_observations += bank_size;
  result.recalc_observations += recalc_size;
  const auto common_size = std::min(bank_size, recalc_size);
  result.compared_observations += common_size;

  bool entry_differs = bank_size != recalc_size;
  if (entry_differs) {
    ++result.length_mismatch_entries;
    result.differing_observations += bank_size >= recalc_size
                                         ? bank_size - recalc_size
                                         : recalc_size - bank_size;
  }

  for (std::size_t index = 0; index < common_size; ++index) {
    const auto bank_bits = floatBits(bank[index]);
    const auto recalc_bits = floatBits(recalc[index]);
    if (bank_bits == recalc_bits) {
      continue;
    }
    entry_differs = true;
    ++result.differing_observations;
    const auto example = makeExample(entry, index, bank[index], recalc[index]);
    if (result.examples.size() < max_examples) {
      result.examples.push_back(example);
    }

    if (std::isfinite(example.delta)) {
      result.min_delta = std::min(result.min_delta, example.delta);
      result.max_delta = std::max(result.max_delta, example.delta);
      const auto magnitude = std::abs(example.delta);
      if (magnitude > result.max_abs_delta) {
        result.max_abs_delta = magnitude;
        result.max_abs_example = example;
      }
    } else {
      ++result.nonfinite_differences;
    }
    if (example.ulp > result.max_ulp) {
      result.max_ulp = example.ulp;
      result.max_ulp_example = example;
    }
  }
  if (entry_differs) {
    ++result.differing_entries;
  }
}

class FieldReader {
 public:
  explicit FieldReader(std::string field, std::string storage)
      : result_{std::move(field), std::move(storage)} {}
  virtual ~FieldReader() = default;
  virtual void compare(long long entry, std::size_t max_examples) = 0;
  Summary result_;
};

class LeafFieldReader final : public FieldReader {
 public:
  LeafFieldReader(TTreeReader& bank_reader, TTreeReader& recalc_reader,
                  const std::string& field)
      : FieldReader(field, "leaf-array"),
        bank_(bank_reader, field.c_str()),
        recalc_(recalc_reader, field.c_str()) {}

  void compare(long long entry, std::size_t max_examples) override {
    std::vector<float> bank_values(bank_.begin(), bank_.end());
    std::vector<float> recalc_values(recalc_.begin(), recalc_.end());
    compareValues(result_, entry, bank_values.data(), bank_values.size(),
                  recalc_values.data(), recalc_values.size(), max_examples);
  }

 private:
  TTreeReaderArray<float> bank_;
  TTreeReaderArray<float> recalc_;
};

class VectorFieldReader final : public FieldReader {
 public:
  VectorFieldReader(TTreeReader& bank_reader, TTreeReader& recalc_reader,
                    const std::string& field)
      : FieldReader(field, "vector<float>"),
        bank_(bank_reader, field.c_str()),
        recalc_(recalc_reader, field.c_str()) {}

  void compare(long long entry, std::size_t max_examples) override {
    const auto& bank_values = *bank_;
    const auto& recalc_values = *recalc_;
    compareValues(result_, entry, bank_values.data(), bank_values.size(),
                  recalc_values.data(), recalc_values.size(), max_examples);
  }

 private:
  TTreeReaderValue<std::vector<float>> bank_;
  TTreeReaderValue<std::vector<float>> recalc_;
};

std::vector<Summary> scanPair(
    const std::string& bank_path, const std::string& recalc_path,
    const std::vector<std::string>& leaf_fields,
    const std::vector<std::string>& vector_fields, std::size_t max_examples) {
  TFile bank_file(bank_path.c_str(), "READ");
  TFile recalc_file(recalc_path.c_str(), "READ");
  if (bank_file.IsZombie()) {
    throw std::runtime_error("cannot open bank file: " + bank_path);
  }
  if (recalc_file.IsZombie()) {
    throw std::runtime_error("cannot open recalc file: " + recalc_path);
  }
  auto* bank_tree = dynamic_cast<TTree*>(bank_file.Get("events"));
  auto* recalc_tree = dynamic_cast<TTree*>(recalc_file.Get("events"));
  if (!bank_tree || !recalc_tree) {
    throw std::runtime_error("missing events tree");
  }
  if (bank_tree->GetEntries() != recalc_tree->GetEntries()) {
    throw std::runtime_error("event count mismatch");
  }

  auto validate = [&](const std::string& field) {
    if (!bank_tree->GetBranch(field.c_str())) {
      throw std::runtime_error("bank branch missing: " + field);
    }
    if (!recalc_tree->GetBranch(field.c_str())) {
      throw std::runtime_error("recalc branch missing: " + field);
    }
  };
  for (const auto& field : leaf_fields) validate(field);
  for (const auto& field : vector_fields) validate(field);

  TTreeReader bank_reader(bank_tree);
  TTreeReader recalc_reader(recalc_tree);
  std::vector<std::unique_ptr<FieldReader>> readers;
  readers.reserve(leaf_fields.size() + vector_fields.size());
  for (const auto& field : leaf_fields) {
    readers.push_back(
        std::make_unique<LeafFieldReader>(bank_reader, recalc_reader, field));
  }
  for (const auto& field : vector_fields) {
    readers.push_back(
        std::make_unique<VectorFieldReader>(bank_reader, recalc_reader, field));
  }

  long long entry = 0;
  while (true) {
    const bool have_bank = bank_reader.Next();
    const bool have_recalc = recalc_reader.Next();
    if (have_bank != have_recalc) {
      throw std::runtime_error("TTreeReader iteration mismatch");
    }
    if (!have_bank) break;
    for (auto& reader : readers) reader->compare(entry, max_examples);
    ++entry;
  }

  std::vector<Summary> results;
  results.reserve(readers.size());
  for (auto& reader : readers) {
    results.push_back(std::move(reader->result_));
  }
  return results;
}

}  // namespace BankRecalcFloatDelta
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-pairs", type=Path, help="bank<TAB>recalc Data pairs")
    parser.add_argument("--mc-pairs", type=Path, help="bank<TAB>recalc MC pairs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=0,
        help="scan at most this many pairs per supplied sample (0 means all)",
    )
    parser.add_argument("--max-examples", type=int, default=5)
    parser.add_argument(
        "--only",
        choices=("data", "mc"),
        help="scan only one sample even when both manifests are supplied",
    )
    parser.add_argument(
        "--update-output",
        action="store_true",
        help="preserve unscanned samples already present in --output",
    )
    return parser.parse_args()


def read_pairs(path: Path, max_pairs: int) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for line_number, raw_line in enumerate(path.read_text().splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 2:
            raise ValueError(f"{path}:{line_number}: expected bank<TAB>recalc")
        result.append((fields[0], fields[1]))
        if max_pairs and len(result) >= max_pairs:
            break
    return result


def cpp_strings(ROOT: Any, values: tuple[str, ...]) -> Any:
    result = ROOT.std.vector("string")()
    for value in values:
        result.push_back(value)
    return result


def clean_number(value: float) -> float | None:
    return value if math.isfinite(value) else None


def example_to_dict(example: Any) -> dict[str, Any]:
    return {
        "entry": int(example.entry),
        "index": int(example.index),
        "bank": float(example.bank),
        "recalc": float(example.recalc),
        "delta_recalc_minus_bank": clean_number(float(example.delta)),
        "ulp_distance": int(example.ulp),
        "bank_bits_hex": f"0x{int(example.bank_bits):08x}",
        "recalc_bits_hex": f"0x{int(example.recalc_bits):08x}",
    }


def summary_to_dict(summary: Any) -> dict[str, Any]:
    differing = int(summary.differing_observations)
    result = {
        "field": str(summary.field),
        "storage": str(summary.storage),
        "entries": int(summary.entries),
        "differing_entries": int(summary.differing_entries),
        "length_mismatch_entries": int(summary.length_mismatch_entries),
        "bank_observations": int(summary.bank_observations),
        "recalc_observations": int(summary.recalc_observations),
        "compared_observations": int(summary.compared_observations),
        "differing_observations": differing,
        "nonfinite_differences": int(summary.nonfinite_differences),
        "min_delta_recalc_minus_bank": (
            clean_number(float(summary.min_delta)) if differing else None
        ),
        "max_delta_recalc_minus_bank": (
            clean_number(float(summary.max_delta)) if differing else None
        ),
        "max_abs_delta": (
            clean_number(float(summary.max_abs_delta)) if differing else 0.0
        ),
        "max_ulp_distance": int(summary.max_ulp),
        "examples": [example_to_dict(value) for value in summary.examples],
        "max_abs_example": (
            example_to_dict(summary.max_abs_example) if differing else None
        ),
        "max_ulp_example": (
            example_to_dict(summary.max_ulp_example) if differing else None
        ),
    }
    return result


def with_pair_provenance(
    example: dict[str, Any] | None, pair_result: dict[str, Any]
) -> dict[str, Any] | None:
    if example is None:
        return None
    return {
        "pair_index": pair_result["pair_index"],
        "bank_path": pair_result["bank"],
        "recalc_path": pair_result["recalc"],
        **example,
    }


def aggregate_fields(
    pair_results: list[dict[str, Any]], max_examples: int
) -> list[dict[str, Any]]:
    aggregates: dict[str, dict[str, Any]] = {}
    count_keys = (
        "entries",
        "differing_entries",
        "length_mismatch_entries",
        "bank_observations",
        "recalc_observations",
        "compared_observations",
        "differing_observations",
        "nonfinite_differences",
    )
    for pair_result in pair_results:
        for field in pair_result["fields"]:
            aggregate = aggregates.get(field["field"])
            if aggregate is None:
                aggregate = {
                    "field": field["field"],
                    "storage": field["storage"],
                    "pairs_scanned": 0,
                    "pairs_with_differences": 0,
                    "pairs_without_differences": 0,
                    "pairs_with_length_mismatches": 0,
                    "pairs_with_nonfinite_differences": 0,
                    **{key: 0 for key in count_keys},
                    "min_delta_recalc_minus_bank": None,
                    "max_delta_recalc_minus_bank": None,
                    "max_abs_delta": 0.0,
                    "max_ulp_distance": 0,
                    "examples": [],
                    "max_abs_example": None,
                    "max_ulp_example": None,
                }
                aggregates[field["field"]] = aggregate
            aggregate["pairs_scanned"] += 1
            if field["differing_observations"]:
                aggregate["pairs_with_differences"] += 1
            else:
                aggregate["pairs_without_differences"] += 1
            if field["length_mismatch_entries"]:
                aggregate["pairs_with_length_mismatches"] += 1
            if field["nonfinite_differences"]:
                aggregate["pairs_with_nonfinite_differences"] += 1
            for key in count_keys:
                aggregate[key] += field[key]

            minimum = field["min_delta_recalc_minus_bank"]
            if minimum is not None and (
                aggregate["min_delta_recalc_minus_bank"] is None
                or minimum < aggregate["min_delta_recalc_minus_bank"]
            ):
                aggregate["min_delta_recalc_minus_bank"] = minimum
            maximum = field["max_delta_recalc_minus_bank"]
            if maximum is not None and (
                aggregate["max_delta_recalc_minus_bank"] is None
                or maximum > aggregate["max_delta_recalc_minus_bank"]
            ):
                aggregate["max_delta_recalc_minus_bank"] = maximum

            if field["max_abs_delta"] > aggregate["max_abs_delta"]:
                aggregate["max_abs_delta"] = field["max_abs_delta"]
                aggregate["max_abs_example"] = with_pair_provenance(
                    field["max_abs_example"], pair_result
                )
            if field["max_ulp_distance"] > aggregate["max_ulp_distance"]:
                aggregate["max_ulp_distance"] = field["max_ulp_distance"]
                aggregate["max_ulp_example"] = with_pair_provenance(
                    field["max_ulp_example"], pair_result
                )
            slots = max_examples - len(aggregate["examples"])
            if slots > 0:
                aggregate["examples"].extend(
                    with_pair_provenance(example, pair_result)
                    for example in field["examples"][:slots]
                )
    return list(aggregates.values())


def scan_sample(
    ROOT: Any,
    name: str,
    pairs: list[tuple[str, str]],
    leaf_fields: tuple[str, ...],
    vector_fields: tuple[str, ...],
    max_examples: int,
) -> dict[str, Any]:
    cpp_leaf_fields = cpp_strings(ROOT, leaf_fields)
    cpp_vector_fields = cpp_strings(ROOT, vector_fields)
    pair_results = []
    started = time.monotonic()
    for pair_index, (bank_path, recalc_path) in enumerate(pairs, 1):
        pair_started = time.monotonic()
        summaries = ROOT.BankRecalcFloatDelta.scanPair(
            bank_path,
            recalc_path,
            cpp_leaf_fields,
            cpp_vector_fields,
            max_examples,
        )
        pair_result = {
            "pair_index": pair_index,
            "bank": bank_path,
            "recalc": recalc_path,
            "elapsed_seconds": time.monotonic() - pair_started,
            "fields": [summary_to_dict(value) for value in summaries],
        }
        pair_results.append(pair_result)
        changed = sum(field["differing_observations"] for field in pair_result["fields"])
        print(
            f"[{name}] {pair_index}/{len(pairs)} "
            f"events={pair_result['fields'][0]['entries']} changed_values={changed} "
            f"seconds={pair_result['elapsed_seconds']:.2f}",
            flush=True,
        )
    return {
        "pairs": len(pairs),
        "elapsed_seconds": time.monotonic() - started,
        "aggregate_fields": aggregate_fields(pair_results, max_examples),
        "pair_results": pair_results,
    }


def main() -> int:
    args = parse_args()
    if not args.data_pairs and not args.mc_pairs:
        raise SystemExit("at least one of --data-pairs or --mc-pairs is required")
    if args.max_pairs < 0 or args.max_examples < 0:
        raise SystemExit("--max-pairs and --max-examples must be nonnegative")

    try:
        import ROOT
    except ImportError as error:
        raise SystemExit("PyROOT is unavailable; source a Key4hep environment") from error

    ROOT.gROOT.SetBatch(True)
    ROOT.gInterpreter.Declare(CPP_HELPER)
    if args.update_output and args.output.exists():
        output = json.loads(args.output.read_text())
        if output.get("format") != "bank-recalc-float-deltas-v1":
            raise SystemExit(f"cannot update unrecognized output: {args.output}")
    else:
        output = {
            "format": "bank-recalc-float-deltas-v1",
            "delta_definition": "recalc minus bank",
            "difference_definition": "IEEE-754 binary32 bit patterns differ",
            "samples": {},
        }

    script_path = Path(__file__).resolve()
    output["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    output["script"] = str(script_path)
    output["script_sha256"] = hashlib.sha256(script_path.read_bytes()).hexdigest()
    manifests = output.setdefault("pair_manifests", {})
    if args.data_pairs:
        manifests["data"] = str(args.data_pairs.resolve())
    if args.mc_pairs:
        manifests["mc"] = str(args.mc_pairs.resolve())

    scan_data = bool(args.data_pairs and args.only != "mc")
    scan_mc = bool(args.mc_pairs and args.only != "data")
    if args.only == "data" and not args.data_pairs:
        raise SystemExit("--only data requires --data-pairs")
    if args.only == "mc" and not args.mc_pairs:
        raise SystemExit("--only mc requires --mc-pairs")
    if scan_data:
        output["samples"]["data"] = scan_sample(
            ROOT,
            "data",
            read_pairs(args.data_pairs, args.max_pairs),
            DATA_LEAF_FIELDS,
            DATA_VECTOR_FIELDS,
            args.max_examples,
        )
    if scan_mc:
        output["samples"]["mc"] = scan_sample(
            ROOT,
            "mc",
            read_pairs(args.mc_pairs, args.max_pairs),
            MC_LEAF_FIELDS,
            MC_VECTOR_FIELDS,
            args.max_examples,
        )

    # Rebuild aggregates for preserved samples too, so an --update-output run
    # upgrades summary bookkeeping without rereading their ROOT files.
    for sample in output["samples"].values():
        sample["aggregate_fields"] = aggregate_fields(
            sample["pair_results"], args.max_examples
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
