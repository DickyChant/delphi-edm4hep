#!/usr/bin/env python3
"""Compare a converted EDM4hep file against its blessed reference.

Differences are detected from the two digests, then explained by reading the
files themselves, so that values are reported rather than hashes. Every
differing collection is examined; the limits below bound only how much is
printed. See README.md.

Reported classes:

  input changed   the selector resolved to a different file
  event identity  the two files hold different events, or the same events in a
                  different order
  no events       the new file is empty
  branch missing  a branch present in the reference is absent
  branch added    a branch not in the reference is present
  content differs one or more branches hold different data
  stack changed   podio, EDM4hep or key4hep version moved. Warning only.

Usage:
  compare_digest.py REF.json NEW.json [--sample ID]
                    [--ref-root A.root --new-root B.root] [--summary FILE]
                    [--max-entries N] [--max-collections N]

Exits 1 if any failure class was reported, 0 otherwise.
"""
import argparse, json, sys

import numpy as np
import awkward as ak
import uproot

MAX_ENTRIES = 10        # differing entries printed per collection
MAX_COLLECTIONS = 10    # collections whose entry table is printed
MAX_NOTES = 25          # rows printed in the summary table
SCAN_LIMIT = 5000       # events examined by the fallback comparison path


class ConvertedFile:
    """One converted EDM4hep file: event identifiers and branch access."""

    def __init__(self, path):
        self.path = path
        self.tree = uproot.open(path)["events"]
        self.run, self.event = self._event_ids()

    def _event_ids(self):
        """(run, event) per entry, or (None, None) if not recorded.

        The DELPHI run and event numbers are stored as generic parameters and
        matched by name suffix: the current converter writes
        sDST_EVT_runNumber, earlier ones wrote runNumber.
        """
        try:
            keys = [str(k) for k in ak.to_list(self.tree["GPIntKeys"].array()[0])]
            vals = self.tree["GPIntValues"].array()

            def find(suffix):
                for i, k in enumerate(keys):
                    if k.lower().endswith(suffix.lower()):
                        return i
                return None

            i_run, i_evt = find("runNumber"), find("eventNumber")
            if i_run is None or i_evt is None:
                return None, None
            return ak.to_numpy(vals[:, i_run, 0]), ak.to_numpy(vals[:, i_evt, 0])
        except Exception:
            return None, None

    def is_leaf(self, branch):
        """True for a branch with no sub-branches.

        Parent record branches hold the same data as their members and cannot
        be compared elementwise, so only leaves are examined.
        """
        try:
            return not len(self.tree[branch].branches)
        except Exception:
            return False

    def array(self, branch):
        return self.tree[branch].array()

    def label(self, i):
        """(run, event) for entry i, falling back to the entry index."""
        if self.run is None:
            return "-", i
        return self.run[i], self.event[i]


class BranchDiff:
    """Which events differ between one branch of two files, and how."""

    def __init__(self, ref_arr, new_arr):
        self.a, self.b = ref_arr, new_arr
        self.multiplicity, self.values, self.exact = self._compare()

    def _compare(self):
        """(events differing in object count, events differing in value, exact).

        The vectorised path covers numeric branches, jagged or with fixed-size
        vector members. Branches awkward cannot broadcast - strings, records -
        fall through to a bounded element-by-element comparison; `exact` is
        False if that scan stopped early.
        """
        a, b = self.a, self.b
        try:
            na, nb = ak.num(a, axis=1), ak.num(b, axis=1)
            same = ak.to_numpy(na == nb)
            mult = np.nonzero(~same)[0]
            vals = np.array([], int)
            if same.any():
                neq = a[same] != b[same]
                while neq.ndim > 1:              # collapse vector members
                    neq = ak.any(neq, axis=-1)
                vals = np.nonzero(same)[0][np.nonzero(ak.to_numpy(neq))[0]]
            return mult, vals, True
        except Exception:
            pass

        try:                                     # one scalar per event
            return (np.array([], int),
                    np.nonzero(ak.to_numpy(a) != ak.to_numpy(b))[0], True)
        except Exception:
            pass

        limit = min(len(a), len(b), SCAN_LIMIT)
        mult, vals = [], []
        la, lb = ak.to_list(a[:limit]), ak.to_list(b[:limit])
        for i in range(limit):
            if la[i] == lb[i]:
                continue
            if isinstance(la[i], list) and isinstance(lb[i], list) \
                    and len(la[i]) != len(lb[i]):
                mult.append(i)
            else:
                vals.append(i)
        return (np.array(mult, int), np.array(vals, int),
                limit == min(len(a), len(b)))

    @property
    def events(self):
        return set(self.multiplicity.tolist()) | set(self.values.tolist())

    def first_difference(self, i):
        """(position, reference value, new value) for event i.

        Position is the index within that event's flattened values, i.e. which
        object of the collection in storage order.
        """
        try:
            ea = ak.to_numpy(ak.flatten(self.a[i:i + 1], axis=None))
            eb = ak.to_numpy(ak.flatten(self.b[i:i + 1], axis=None))
        except Exception:
            return "-", str(ak.to_list(self.a[i]))[:40], str(ak.to_list(self.b[i]))[:40]
        n = min(len(ea), len(eb))
        j = np.nonzero(ea[:n] != eb[:n])[0]
        if len(j) == 0:
            return "n", f"n={len(ea)}", f"n={len(eb)}"
        j = int(j[0])
        return j, ea[j], eb[j]


class CollectionReport:
    """Everything found for one collection: which members, which events."""

    def __init__(self, name):
        self.name = name
        self.members = []          # branch names that differ
        self.events = set()        # entries affected, across all members
        self.partial = False       # a fallback scan stopped early
        self.rows = []             # sample rows for printing

    @property
    def summary(self):
        return (f"{len(self.members)} member(s) differ, "
                f"{'>=' if self.partial else ''}{len(self.events)} event(s) affected")


class Comparison:
    """Reference-versus-new comparison of one sample."""

    def __init__(self, ref, new, ref_root=None, new_root=None,
                 max_entries=MAX_ENTRIES, max_collections=MAX_COLLECTIONS,
                 columns=("reference", "new")):
        self.ref, self.new = ref, new
        self.columns = columns          # table headings for the two sides
        self.ref_root, self.new_root = ref_root, new_root
        self.max_entries, self.max_collections = max_entries, max_collections
        self.fails, self.warns, self.notes = [], [], []
        self.changed, self.reports = [], []

    @property
    def failed(self):
        return bool(self.fails)

    # ------------------------------------------------------------- stage 1 --
    def detect(self):
        """Digest-level comparison; fills fails/warns/notes and self.changed."""
        ri, ni = self.ref.get("input"), self.new.get("input")
        if ri and ni and ri != ni:
            bad, info = self._input_notes(ri, ni)
            self.notes.extend(info)          # e.g. a different mount root
            if bad:
                self.fails.append("input changed")
                self.notes.extend(bad)

        rp, np_ = self.ref["payload"], self.new["payload"]
        if np_["entries"] == 0:
            self.fails.append("no events")
            self.notes.append(("no events", "events", str(rp["entries"]), "0"))
        if rp["entries"] != np_["entries"]:
            self.fails.append("event count differs")
            self.notes.append(("event count", "events",
                               str(rp["entries"]), str(np_["entries"])))

        rb, nb = rp["branches"], np_["branches"]
        for b in sorted(set(rb) - set(nb)):
            self.fails.append("branch missing")
            self.notes.append(("branch missing", b, "present", "-"))
        for b in sorted(set(nb) - set(rb)):
            self.fails.append("branch added")
            self.notes.append(("branch added", b, "-", "present"))

        self.changed = [b for b in sorted(set(rb) & set(nb)) if rb[b] != nb[b]]
        if self.changed:
            self.fails.append("content differs")

        if self.ref.get("stack") != self.new.get("stack"):
            self.warns.append("stack changed")
            rs, ns = self.ref.get("stack", {}), self.new.get("stack", {})
            for k in sorted(set(rs) | set(ns)):
                if k != "collections" and rs.get(k) != ns.get(k):
                    self.notes.append(("stack changed (warn)", k,
                                       str(rs.get(k)), str(ns.get(k))))

    @staticmethod
    def _input_notes(ri, ni):
        """How two input manifests differ.

        Returns (failures, notes). A different selector, input directive or file
        content is a failure. The data root is recorded as a note only, since
        files are identified by their catalog-relative name.
        """
        rows, info = [], []
        if ri.get("selector") != ni.get("selector"):
            rows.append(("input selector", "samples.yaml",
                         str(ri.get("selector")), str(ni.get("selector"))))
        if ri.get("data_root") != ni.get("data_root"):
            info.append(("data root (note)", "DELPHI_DATA_ROOT",
                         str(ri.get("data_root")), str(ni.get("data_root"))))
        if ri.get("pdlinput") != ni.get("pdlinput"):
            rows.append(("input directive", "PDLINPUT",
                         str(ri.get("pdlinput")), str(ni.get("pdlinput"))))
        # Keyed on the catalog-relative name rather than the mounted path, so
        # that reading the same file through a different EOS area compares equal.
        def key(f):
            return f.get("name") or f["path"]

        rf = {key(f): f for f in ri.get("files", [])}
        nf = {key(f): f for f in ni.get("files", [])}
        for k in sorted(set(rf) - set(nf)):
            rows.append(("input file gone", k, f"{rf[k].get('size')} B", "-"))
        for k in sorted(set(nf) - set(rf)):
            rows.append(("input file new", k, "-", f"{nf[k].get('size')} B"))
        for k in sorted(set(rf) & set(nf)):
            x, y = rf[k], nf[k]
            if x.get("sha256") != y.get("sha256"):
                rows.append(("input file changed", k,
                             f"{x.get('size')} B {str(x.get('sha256'))[:12]}",
                             f"{y.get('size')} B {str(y.get('sha256'))[:12]}"))
        return rows, info

    # ------------------------------------------------------------- stage 2 --
    def collection_of(self, branch):
        """The EDM4hep collection a branch belongs to.

        Branch names take several forms - plain member, relation, vector member
        - so rather than parsing them, the collection names recorded in the file
        metadata are matched against the branch name. The longest match wins,
        because one collection name can be a prefix of another
        (sDST_HAID_dEdx and sDST_HAID_dEdxVD).
        """
        names = (self.new.get("stack", {}).get("collections") or {}).keys()
        hits = [c for c in names if c in branch]
        if hits:
            return max(hits, key=len)
        return branch.split("/")[0].split(".")[0].lstrip("_")

    def explain(self):
        """Examine every differing collection and collect sample rows."""
        ref = ConvertedFile(self.ref_root)
        new = ConvertedFile(self.new_root)
        self._check_event_identity(ref, new)

        groups = {}
        for b in self.changed:
            if ref.is_leaf(b):
                groups.setdefault(self.collection_of(b), []).append(b)

        for coll in sorted(groups):
            rep = CollectionReport(coll)
            for b in groups[coll]:
                try:
                    diff = BranchDiff(ref.array(b), new.array(b))
                except Exception as e:
                    rep.members.append(b)
                    rep.rows.append(("-", "-", b.split("/")[-1], "-",
                                     f"uncomparable: {type(e).__name__}", "-"))
                    continue
                rep.members.append(b)
                rep.events |= diff.events
                rep.partial = rep.partial or not diff.exact
                self._add_rows(rep, diff, b, new)
            self.reports.append(rep)

    def _add_rows(self, rep, diff, branch, new):
        """Append up to max_entries sample rows for one branch."""
        member = branch.split("/")[-1]
        room = self.max_entries - len(rep.rows)
        if room <= 0:
            return
        for i in list(diff.multiplicity)[:room]:
            run, evt = new.label(i)
            rep.rows.append((run, evt, member, "n",
                             f"n={len(diff.a[i])}", f"n={len(diff.b[i])}"))
        room = self.max_entries - len(rep.rows)
        for i in list(diff.values)[:room]:
            run, evt = new.label(i)
            j, x, y = diff.first_difference(i)
            rep.rows.append((run, evt, member, j, x, y))

    def _check_event_identity(self, ref, new):
        """Confirm the two files line up event for event before comparing values."""
        if ref.run is None or new.run is None:
            return
        n = min(len(ref.run), len(new.run))
        bad = np.nonzero((ref.run[:n] != new.run[:n]) |
                         (ref.event[:n] != new.event[:n]))[0]
        if len(bad):
            self.fails.append("event identity")
            for i in bad[:MAX_NOTES]:
                self.notes.append(("event identity", f"entry {int(i)}",
                                   f"run {ref.run[i]} evt {ref.event[i]}",
                                   f"run {new.run[i]} evt {new.event[i]}"))

    # ----------------------------------------------------------- rendering --
    def render(self, sample):
        verdict = "FAIL" if self.fails else \
                  ("pass (with warnings)" if self.warns else "pass")
        out = [f"### {sample} — {verdict}\n"]

        left, right = self.columns
        if self.notes:
            out.append(f"| class | what | {left} | {right} |")
            out.append("|---|---|---|---|")
            for c, b, r, n in self.notes[:MAX_NOTES]:
                out.append(f"| {c} | `{b}` | {r} | {n} |")
            if len(self.notes) > MAX_NOTES:
                out.append(f"| … | _{len(self.notes) - MAX_NOTES} more_ | | |")
            out.append("")

        if self.reports:
            out.append(f"**{len(self.reports)} collection(s) differ** "
                       f"({len(self.changed)} branches):\n")
            # Every collection is listed, so the inventory is complete; only the
            # first max_collections get their entry table printed.
            for i, rep in enumerate(self.reports):
                out.append(f"#### `{rep.name}` — {rep.summary}\n")
                if i < self.max_collections and rep.rows:
                    out.append(f"| run | event | member | idx | {left} | {right} |")
                    out.append("|---|---|---|---|---|---|")
                    for r in rep.rows:
                        out.append("| " + " | ".join(str(x) for x in r) + " |")
                    out.append("")
                elif i == self.max_collections:
                    out.append("_entry tables above this point only._\n")
        return "\n".join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ref"); p.add_argument("new")
    p.add_argument("--sample", default="sample")
    p.add_argument("--ref-root", default=None); p.add_argument("--new-root", default=None)
    p.add_argument("--summary", default=None, help="append the report to this file")
    p.add_argument("--max-entries", type=int, default=MAX_ENTRIES)
    p.add_argument("--max-collections", type=int, default=MAX_COLLECTIONS)
    a = p.parse_args()

    with open(a.ref) as fh:
        ref = json.load(fh)
    with open(a.new) as fh:
        new = json.load(fh)

    cmp_ = Comparison(ref, new, a.ref_root, a.new_root,
                      a.max_entries, a.max_collections)
    cmp_.detect()
    if cmp_.changed and a.ref_root and a.new_root:
        cmp_.explain()
    elif cmp_.changed:
        cmp_.notes.append(("content differs", f"{len(cmp_.changed)} branches",
                           "rerun with --ref-root/--new-root", "for value detail"))

    md = cmp_.render(a.sample)
    print(md)
    if a.summary:
        with open(a.summary, "a") as fh:
            fh.write(md + "\n")
    return 1 if cmp_.failed else 0


if __name__ == "__main__":
    sys.exit(main())
