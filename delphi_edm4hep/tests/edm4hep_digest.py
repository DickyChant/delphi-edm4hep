#!/usr/bin/env python3
"""Compute a content digest of a converted EDM4hep file.

The digest has two sections:

  payload  one entry per branch of the `events` tree: element count, storage
           type, and a hash of the values in order.
  stack    podio and EDM4hep versions, per-collection schema versions, and the
           key4hep release.

See README.md for how the two are used.

Usage:
  edm4hep_digest.py FILE [--key4hep REL] [--out OUT.json]
"""
import argparse, hashlib, json, sys

import numpy as np
import awkward as ak
import uproot

# Increment when the JSON layout changes incompatibly, so that older reference
# files can be recognised instead of mis-compared.
SCHEMA = 1

# Hash prefix kept per branch, in hex characters.
SHA_CHARS = 16


def _hash_array(arr):
    """Element count, dtype and value hash for one branch.

    ak.flatten(axis=None) reduces any nesting - per-event lists, vector members,
    fixed-size covariance blocks - to a flat array, so all branch shapes are
    handled uniformly. The dtype is part of the hash, so a change of storage
    type is detected even when the values are unchanged.
    """
    try:
        flat = ak.to_numpy(ak.flatten(arr, axis=None))
    except Exception:
        # Branches numpy cannot hold, such as the variable-length strings in
        # the generic-parameter branches.
        flat = np.asarray(ak.to_list(arr), dtype=object)
    h = hashlib.sha256()
    h.update(str(flat.dtype).encode())
    if flat.dtype == object:
        h.update(repr(flat.tolist()).encode())
    else:
        h.update(np.ascontiguousarray(flat).tobytes())
    return {"n": int(len(flat)), "dtype": str(flat.dtype), "sha": h.hexdigest()[:SHA_CHARS]}


def _stack(f):
    """Version and schema information from the podio_metadata tree.

    Returns an empty dict for files without that tree.
    """
    out = {}
    if "podio_metadata" not in [k.split(";")[0] for k in f.keys(recursive=False)]:
        return out
    md = f["podio_metadata"]
    for label, branch in (("podio", "PodioBuildVersion"), ("edm4hep", "edm4hep___Version")):
        try:
            v = md[branch].array()[0]
            out[label] = f"{v['major']}.{v['minor']}.{v['patch']}"
        except Exception:
            pass          # branch absent or renamed in this podio version
    try:
        # Datatype and schema version per collection. A podio schema evolution
        # appears here rather than in the payload.
        ti = md["events___CollectionTypeInfo"].array()[0]
        out["collections"] = {
            str(r["name"]): {
                "type": str(r["dataType"]),
                "schemaVersion": int(r["schemaVersion"]),
                "collectionID": int(r["collectionID"]),
            }
            for r in ti
        }
    except Exception:
        pass
    return out


def digest(path, key4hep=None):
    """Return {schema, payload, stack} for one converted file.

    uproot's keys() is recursive, so a parent record branch and each of its
    members are hashed separately.
    """
    f = uproot.open(path)
    ev = f["events"]
    payload = {
        "entries": int(ev.num_entries),
        "branches": {b: _hash_array(ev[b].array()) for b in sorted(ev.keys())},
    }
    st = _stack(f)
    if key4hep:
        # Supplied by the caller: the release is a property of the environment
        # and is not recorded in the file.
        st["key4hep_release"] = key4hep
    return {"schema": SCHEMA, "payload": payload, "stack": st}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("--key4hep", default=None, help="key4hep release, recorded under stack")
    p.add_argument("--out", default=None, help="write JSON here instead of stdout")
    a = p.parse_args()
    d = digest(a.file, a.key4hep)
    # Sorted keys so two digests of equal content are textually identical and
    # can be compared with diff.
    txt = json.dumps(d, indent=1, sort_keys=True)
    if a.out:
        open(a.out, "w").write(txt + "\n")
        print(f"digest: {a.out}  ({d['payload']['entries']} events, "
              f"{len(d['payload']['branches'])} branches)")
    else:
        print(txt)


if __name__ == "__main__":
    sys.exit(main())
