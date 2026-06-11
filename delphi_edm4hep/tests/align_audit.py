#!/usr/bin/env python3
"""Alignment / relation audit for delphi_edm4hep EDM4hep output.

For every UserDataCollection the converter emits, the README documents which
object collection it runs parallel to (index-aligned). This scanner checks
those length contracts on a real EDM4hep file, plus the RecDqdx -> Track
relation. It is the regression guard for the bug class where a per-particle
array is mislabelled as per-track (so consumers indexing by track read the
wrong row), or a relation is silently left unset -- neither of which the
momentum/value-level checks (thrust, "dE/dx non-zero") can see. The failure is
only visible on events that contain a reco neutral (Particles > Tracks), e.g.
Z->mumu(gamma): a clean 2-track event has Particles==Tracks and hides it.

Usage:
    align_audit.py <file.edm4hep.root>
    DELPHI_EDM4HEP_SAMPLE=<file.edm4hep.root> align_audit.py

Exit 0 if all contracts hold (or no input is given -> skipped, so the CTest is
a no-op until a sample is provided). Exit 1 if any contract fails.
"""
import os
import sys

# README parallelism contracts: UserData collection -> collection it must
# match in length, event by event.
LENGTH_CONTRACTS = {
    "sDST_TRAC_d0PV":              "sDST_TRAC_Tracks",
    "sDST_TRAC_z0PV":              "sDST_TRAC_Tracks",
    "sDST_TRAC_d0BS":              "sDST_TRAC_Tracks",
    "sDST_VECP_LVLOCK":            "sDST_MAIN_Particles",
    "sDST_PV_Vertices_StatusBits": "sDST_PV_Vertices",
    "sDST_TDVD_VDHits_TrackIndex": "sDST_TDVD_VDHits",
    "sDST_ELTR_ParticleIndex":     "sDST_ELTR_RefitTracks",
    "fDST_MAIN_MatchProvenance":   "fDST_MAIN_Particles",
}


def main():
    fn = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] \
        else os.environ.get("DELPHI_EDM4HEP_SAMPLE", "")
    if not fn:
        print("align_audit: no input (pass a file or set DELPHI_EDM4HEP_SAMPLE)"
              " -> skipping")
        return 0
    if not os.path.exists(fn):
        print(f"align_audit: {fn} not found -> skipping")
        return 0

    from podio import root_io
    reader = root_io.Reader(fn)

    len_fail = {}   # (userdata, parallel) -> [(event, got, expected), ...]
    dq_missing = dq_total = nev = 0
    for i, fr in enumerate(reader.get("events")):
        nev += 1
        names = set(fr.getAvailableCollections())
        size = lambda n: fr.get(n).size() if n in names else None
        for ud, par in LENGTH_CONTRACTS.items():
            a, b = size(ud), size(par)
            if a is not None and b is not None and a != b:
                len_fail.setdefault((ud, par), []).append((i, a, b))
        for n in names:
            if n.endswith("_RecDqdx"):
                for dq in fr.get(n):
                    dq_total += 1
                    if dq.getTrack().getObjectID().index < 0:
                        dq_missing += 1

    print(f"align_audit: {fn}  ({nev} events)")
    ok = True
    if len_fail:
        ok = False
        for (ud, par), lst in sorted(len_fail.items()):
            e = lst[0]
            print(f"  FAIL  len({ud}) != len({par}) in {len(lst)}/{nev} events "
                  f"(e.g. evt{e[0]}: {e[1]} vs {e[2]})")
    else:
        print(f"  OK    all {len(LENGTH_CONTRACTS)} length contracts hold")
    if dq_missing:
        ok = False
        print(f"  FAIL  {dq_missing}/{dq_total} RecDqdx rows missing a Track link")
    elif dq_total:
        print(f"  OK    all {dq_total} RecDqdx rows carry a Track link")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
