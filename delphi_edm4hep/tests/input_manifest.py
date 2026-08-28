#!/usr/bin/env python3
"""Record which input files a conversion actually read, into its digest.

Samples are selected indirectly: samples.yaml names a fatfind nickname, and
fatfind resolves it through RunInfo and the PDL files on cvmfs. Those are
maintained upstream, so the file behind a nickname can change. This script
records the resolved input alongside the content digest, which lets
compare_digest.py distinguish a changed input from a changed converter.

The resolved paths are taken from the converter's own log. PHDST rewrites
`FAT = <nickname>` into `FILE = <path>` internally and reports each file it
opens as

    Open file /eos/opendata/delphi/collision-data/Y13709/Y13709.1.al

so the same parsing works for the -N, -P and plain-path input modes.

Usage:
  input_manifest.py --mode M --value V --pdlinput PDLINPUT --log LOG --into D.json

Adds an "input" section to the digest JSON at --into and exits non-zero if the
log shows no file was opened.
"""
import argparse, hashlib, json, os, re, sys
from pathlib import Path

# PHDST also logs lines such as "AAOPEN - Open file of type RD:P94C2FRD.611",
# which match this pattern without naming a path. Callers must keep the
# absolute-path check in opened_files().
OPENED = re.compile(r"Open file\s+(\S+)")


def catalog_name(path):
    """Name of an input file relative to $DELPHI_DATA_ROOT.

    The same DELPHI file is reached through different roots depending on what is
    mounted, for example

        /eos/opendata/delphi/collision-data/Y13709/Y13709.1.al
        /eos/experiment/delphi/castor2015/tape/Y13709/Y13709.1.al

    The relative name identifies the file in the catalog in either case. Falls
    back to the basename when the path lies outside the data root.
    """
    root = os.environ.get("DELPHI_DATA_ROOT")
    if root:
        try:
            rel = os.path.relpath(path, root)
            if not rel.startswith(".."):
                return rel
        except ValueError:
            pass
    return os.path.basename(path)


def sha256(path, chunk=1 << 20):
    """SHA-256 of a file's full contents. About 0.3 s per 90 MB."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def opened_files(log):
    """Absolute paths reported as opened in a converter log.

    Duplicates are removed and the original order kept: for a multi-file
    dataset read under an event cap, the order determines which data was used.
    """
    seen, out = set(), []
    for line in Path(log).read_text(errors="replace").splitlines():
        m = OPENED.search(line)
        if m and m.group(1).startswith("/") and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


def build(mode, value, pdlinput, log):
    """Return the input manifest for one conversion, or None if nothing opened."""
    files = []
    for f in opened_files(log):
        try:
            st = Path(f).stat()
            files.append({"name": catalog_name(f), "path": f,
                          "size": st.st_size, "sha256": sha256(f)})
        except OSError as e:
            files.append({"name": catalog_name(f), "path": f,
                          "error": type(e).__name__})
    if not files:
        return None
    pdl = Path(pdlinput)
    return {
        "selector": {"mode": mode, "value": value},
        "pdlinput": pdl.read_text().strip() if pdl.exists() else None,
        "files": files,
        "data_root": os.environ.get("DELPHI_DATA_ROOT"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, help="nickname | pdl | file")
    p.add_argument("--value", required=True, help="the selector from samples.yaml")
    p.add_argument("--pdlinput", required=True, help="PDLINPUT written by the harness")
    p.add_argument("--log", required=True, help="converter log to parse")
    p.add_argument("--into", required=True, help="digest JSON to extend")
    a = p.parse_args()

    files = []
    for f in opened_files(a.log):
        try:
            st = Path(f).stat()
            files.append({"name": catalog_name(f), "path": f,
                          "size": st.st_size, "sha256": sha256(f)})
        except OSError as e:
            # Opened during the conversion but unreadable now. Recorded as an
            # error entry so the file still appears in the manifest.
            files.append({"name": catalog_name(f), "path": f,
                          "error": type(e).__name__})

    if not files:
        print("input_manifest: no opened file found in the log - check for "
              "'error in CFOPEN' in the converter output", file=sys.stderr)
        return 1

    pdl = Path(a.pdlinput)
    manifest = {
        "selector": {"mode": a.mode, "value": a.value},   # requested
        "pdlinput": pdl.read_text().strip() if pdl.exists() else None,  # as given to PHDST
        "files": files,                                   # actually opened
        "data_root": os.environ.get("DELPHI_DATA_ROOT"),  # root the paths are under
    }

    # Stored inside the digest so that one file describes a reference
    # completely: content hashes, stack versions and input provenance.
    d = json.loads(Path(a.into).read_text())
    d["input"] = manifest
    Path(a.into).write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")
    print(f"input: {len(manifest['files'])} file(s), "
          f"first = {manifest['files'][0]['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
