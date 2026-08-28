#!/usr/bin/env python3
"""Run the equivalence checks declared in samples.yaml.

Each check names one physical file reached two ways - by fatfind nickname, by
PDL file, or by explicit path. Both sides are converted with the same binary in
the same run and compared against each other, so no blessed reference is used.

Usage:
  equivalence.py --bin BIN --work DIR --tests DIR --key4hep REL [--summary FILE]

Exits 1 if any check failed.
"""
import argparse, sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import converter                           # noqa: E402
from edm4hep_digest import digest          # noqa: E402
from compare_digest import Comparison      # noqa: E402


class EquivalenceCheck:
    """One entry from the equivalence section of samples.yaml."""

    def __init__(self, spec, binary, work, key4hep, max_entries, max_collections):
        self.id = spec["id"]
        self.a, self.b = spec["a"], spec["b"]
        self.max_events = spec.get("max_events", -1)
        self.binary = binary
        self.work = Path(work) / self.id
        self.key4hep = key4hep
        self.max_entries, self.max_collections = max_entries, max_collections

    def run(self):
        """Convert both sides and compare them. Returns (markdown, ok)."""
        label = f'{self.id} ({self.a["mode"]} vs {self.b["mode"]})'
        sides = {}
        for name, sel in (("a", self.a), ("b", self.b)):
            sides[name] = converter.run(self.binary, sel, self.work / name,
                                        self.max_events)

        failed = [(name, sides[name]) for name in ("a", "b") if not sides[name].ok]
        if failed:
            rows = [("conversion failed", name, (self.a if name == "a" else self.b)["value"],
                     f"{c.message}; see {c.log}") for name, c in failed]
            return _render_failure(label, rows), False

        da = digest(str(sides["a"].root), self.key4hep)
        db = digest(str(sides["b"].root), self.key4hep)

        cmp_ = Comparison(da, db, str(sides["a"].root), str(sides["b"].root),
                          self.max_entries, self.max_collections, columns=("a", "b"))
        cmp_.detect()
        if cmp_.changed:
            cmp_.explain()
        return cmp_.render(label), not cmp_.failed


def _render_failure(label, rows):
    out = [f"### {label} — FAIL\n",
           "| class | side | selector | detail |", "|---|---|---|---|"]
    out += [f"| {c} | {s} | `{v}` | {d} |" for c, s, v, d in rows]
    return "\n".join(out) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bin", required=True, help="delphi_sdst_pass to run")
    p.add_argument("--work", required=True, help="scratch directory")
    p.add_argument("--tests", required=True, help="directory holding samples.yaml")
    p.add_argument("--key4hep", required=True)
    p.add_argument("--summary", default=None, help="append reports to this file")
    p.add_argument("--max-entries", type=int, default=10)
    p.add_argument("--max-collections", type=int, default=10)
    a = p.parse_args()

    spec = yaml.safe_load(Path(a.tests, "samples.yaml").read_text()) or {}
    rc = 0
    for entry in spec.get("equivalence", []):
        md, ok = EquivalenceCheck(entry, a.bin, a.work, a.key4hep,
                                  a.max_entries, a.max_collections).run()
        print(md)
        if a.summary:
            with open(a.summary, "a") as fh:
                fh.write(md + "\n")
        if not ok:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
