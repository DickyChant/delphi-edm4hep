#!/usr/bin/env python3
"""
Dump hadron-tagging features from DELPHI nanoAOD.

Reads the `t` tree and writes a slim parquet table with:
- event-level labels/counts (if present; MC-only in current schema)
- per-particle flavour flags and hemisphere-split variants
"""

import argparse
from pathlib import Path

import awkward as ak
import uproot


EVENT_BRANCHES = [
    "n_Bc_Emin",
    "n_Bs_Emin",
    "n_Bu_Emin",
    "n_Bd_Emin",
    "n_Lb_Emin",
    "n_Bc_Emax",
    "n_Bs_Emax",
    "n_Bu_Emax",
    "n_Bd_Emax",
    "n_Lb_Emax",
    "label_Bc_Emin",
    "label_Bs_Emin",
    "label_Bu_Emin",
    "label_Bd_Emin",
    "label_Lb_Emin",
    "label_light_Emin",
    "label_hasBc_Emin",
    "label_has1Bc_Emin",
    "label_Bc_Emax",
    "label_Bs_Emax",
    "label_Bu_Emax",
    "label_Bd_Emax",
    "label_Lb_Emax",
    "label_light_Emax",
    "label_hasBc_Emax",
    "label_has1Bc_Emax",
]

PART_BRANCHES = [
    "Part_fromBc",
    "Part_fromBs",
    "Part_fromBu",
    "Part_fromBd",
    "Part_fromLb",
    "theta_wrtThrMissP",
]


def _present(tree, names):
    keys = set(tree.keys())
    return [n for n in names if n in keys]


def main():
    parser = argparse.ArgumentParser(description="Dump hadron-tagging features from nanoAOD.")
    parser.add_argument("input_root", help="Input nanoAOD ROOT file.")
    parser.add_argument("-t", "--tree", default="t", help="Input tree name (default: t).")
    parser.add_argument(
        "-o",
        "--output",
        default="hadron_tagging.parquet",
        help="Output parquet path (default: hadron_tagging.parquet).",
    )
    args = parser.parse_args()

    in_path = Path(args.input_root)
    out_path = Path(args.output)

    with uproot.open(in_path) as f:
        tree = f[args.tree]
        wanted = _present(tree, EVENT_BRANCHES + PART_BRANCHES)
        if not wanted:
            raise RuntimeError("No hadron-tagging branches found in input tree.")
        arr = tree.arrays(wanted, library="ak")

    if "theta_wrtThrMissP" in arr.fields:
        theta = arr["theta_wrtThrMissP"]
        is_emin = theta > 0
        is_emax = theta < 0
        for base in ("Part_fromBc", "Part_fromBs", "Part_fromBu", "Part_fromBd", "Part_fromLb"):
            if base in arr.fields:
                arr[f"{base}_Emin"] = arr[base][is_emin]
                arr[f"{base}_Emax"] = arr[base][is_emax]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ak.to_parquet(arr, out_path)
    print(f"Wrote {out_path}")
    print("Branches:", ", ".join(arr.fields))


if __name__ == "__main__":
    main()

