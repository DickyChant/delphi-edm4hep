#!/usr/bin/env python3
"""Convert every sample in samples.yaml and compare it against its reference.

Two modes:

  normal    each sample is converted, digested, and compared against the
            blessed reference held under --refs. Differences are reported and
            the exit code is non-zero.
  --bless   the reference is regenerated instead, and refs.lock updated. Use
            when a difference has been reviewed and accepted, or to create a
            reference for a newly added sample.

The equivalence checks in samples.yaml run afterwards in both modes; they
compare two fresh conversions with each other and need no reference.

The DELPHI and key4hep environments must already be set up; see
.github/scripts/data-test.sh, which does that and then calls this.

Usage:
  run_tests.py --bin BIN --work DIR --refs DIR --key4hep REL
               [--bless] [--summary FILE] [ID ...]

With no ID arguments every sample runs. Exits 1 if any sample or check failed.
"""
import argparse, json, shutil, subprocess, sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import converter                            # noqa: E402
import input_manifest                       # noqa: E402
import refs_lock                            # noqa: E402
from edm4hep_digest import digest           # noqa: E402
from compare_digest import Comparison       # noqa: E402
from equivalence import EquivalenceCheck    # noqa: E402

HERE = Path(__file__).resolve().parent

# Files making up one blessed reference. The digest is what the comparison
# reads; the .root is kept so that differences can be reported as values
# rather than as hashes.
REF_DIGEST = "ref.digest.json"
REF_ROOT = "ref.edm4hep.root"


class SampleTest:
    """One entry from the samples section of samples.yaml.

    Two directories are involved: a scratch directory under --work, holding
    this run's conversion, and a reference directory under --refs, holding the
    blessed one.
    """

    def __init__(self, spec, opts):
        self.id = spec["id"]
        self.selector = spec["select"]
        self.max_events = spec.get("max_events", -1)
        self.kind = spec["kind"]
        self.opts = opts
        self.work = Path(opts.work) / self.id
        self.ref_dir = Path(opts.refs) / self.id

    def convert(self):
        """Convert this sample and describe the result.

        Returns (digest, conversion) on success. On failure the first element
        is None and the second is the report to print, so the caller does not
        need to distinguish the two failure causes.
        """
        conv = converter.run(self.opts.bin, self.selector, self.work,
                             self.max_events)
        if not conv.ok:
            return None, _fail(self.id, "conversion failed",
                               f"{conv.message}; see {conv.log}")

        d = digest(str(conv.root), self.opts.key4hep)

        # Which files the converter actually opened. Recorded in the digest so
        # that a later difference can be attributed to a changed input rather
        # than to the converter.
        manifest = input_manifest.build(self.selector["mode"],
                                        self.selector["value"],
                                        conv.pdlinput, conv.log)
        if manifest is None:
            return None, _fail(self.id, "no input opened",
                               f"no 'Open file' line in {conv.log}")
        d["input"] = manifest
        return d, conv

    def bless(self, d, conv):
        """Install this conversion as the reference.

        Writes three things: the digest and the converted file into the
        reference directory on this machine, and a provenance block into
        refs.lock, which is committed.
        """
        self.ref_dir.mkdir(parents=True, exist_ok=True)
        (self.ref_dir / REF_DIGEST).write_text(json.dumps(d, indent=1,
                                                          sort_keys=True) + "\n")
        shutil.copyfile(conv.root, self.ref_dir / REF_ROOT)
        sha = refs_lock.update(self.opts.lock, self.id, d, self.opts.key4hep)
        return (f"### {self.id} — blessed\n\n"
                f"{d['payload']['entries']} events, "
                f"{len(d['payload']['branches'])} branches, payload `{sha}`\n"), True

    def compare(self, d, conv):
        """Compare this conversion against the blessed reference."""
        ref_digest = self.ref_dir / REF_DIGEST
        if not ref_digest.exists():
            return _fail(self.id, "no reference",
                         f"{ref_digest} missing; run with --bless"), False
        ref = json.loads(ref_digest.read_text())
        cmp_ = Comparison(ref, d, str(self.ref_dir / REF_ROOT), str(conv.root),
                          self.opts.max_entries, self.opts.max_collections)
        cmp_.detect()
        # Reading the files back is only needed when something differs.
        if cmp_.changed:
            cmp_.explain()
        return cmp_.render(self.id), not cmp_.failed

    def check(self, conv):
        """Content checks on the converted file. Returns (markdown, ok).

        These read the pass-1 output only, so they run in --bless mode too:
        blessing a file that fails its own content checks would install a
        broken reference.
        """
        runs = [
            ("align_audit",
             [sys.executable, str(HERE / "align_audit.py"), str(conv.root)]),
            ("btag_check",
             [self.opts.btag_check, "--source", "sDST", str(conv.root),
              self.kind]),
        ]
        rows, ok = [], True
        for name, cmd in runs:
            r = subprocess.run(cmd, text=True, capture_output=True)
            # 77 is the CTest skip code, which these tools use when they have
            # nothing to work on. Not a failure.
            passed = r.returncode in (0, 77)
            ok = ok and passed
            lines = [l.strip() for l in (r.stdout or r.stderr).splitlines()
                     if l.strip()]
            # On failure the failing lines are the point; otherwise summarise.
            shown = [l for l in lines if "FAIL" in l] or lines
            detail = "; ".join(shown)[:300] or "(no output)"
            rows.append(f"| {name} | {'ok' if passed else 'FAIL'} | {detail} |")
        md = (f"### {self.id} — content checks\n\n"
              "| check | result | detail |\n|---|---|---|\n"
              + "\n".join(rows) + "\n")
        return md, ok

    def run(self):
        """Convert, check, then either bless or compare. Returns (markdown, ok)."""
        d, conv = self.convert()
        if d is None:
            return conv, False              # conv holds the failure report
        check_md, check_ok = self.check(conv)
        if self.opts.bless:
            md, ok = self.bless(d, conv)
        else:
            md, ok = self.compare(d, conv)
        return md + "\n" + check_md, ok and check_ok


def _fail(sample, cls, detail):
    """A one-row report, for failures that never reach a comparison."""
    return (f"### {sample} — FAIL\n\n"
            "| class | detail |\n|---|---|\n"
            f"| {cls} | {detail} |\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ids", nargs="*", help="samples to run (default: all)")
    p.add_argument("--bin", required=True, help="delphi_sdst_pass to run")
    p.add_argument("--btag-check", required=True, help="delphi_btag_check to run")
    p.add_argument("--work", required=True, help="scratch directory")
    p.add_argument("--refs", required=True, help="directory holding the references")
    p.add_argument("--key4hep", required=True, help="release, recorded in the digest")
    p.add_argument("--bless", action="store_true", help="regenerate the references")
    p.add_argument("--summary", default=None, help="append reports to this file")
    p.add_argument("--lock", default=str(HERE / "refs.lock"),
                   help="provenance file to update when blessing")
    p.add_argument("--max-entries", type=int, default=10)
    p.add_argument("--max-collections", type=int, default=10)
    p.add_argument("--tests", default=str(HERE), help="directory holding samples.yaml")
    opts = p.parse_args()

    spec = yaml.safe_load(Path(opts.tests, "samples.yaml").read_text()) or {}
    samples = {s["id"]: s for s in spec.get("samples", [])}

    # An unrecognised id is an error rather than a silent skip.
    wanted = opts.ids or list(samples)
    unknown = [i for i in wanted if i not in samples]
    if unknown:
        print(f"unknown sample id(s): {', '.join(unknown)}", file=sys.stderr)
        return 1

    # Every sample and every check runs even if an earlier one failed, so that
    # one report covers the whole state rather than stopping at the first fault.
    reports, rc = [], 0
    for sid in wanted:
        md, ok = SampleTest(samples[sid], opts).run()
        reports.append(md)
        if not ok:
            rc = 1

    for entry in spec.get("equivalence", []):
        md, ok = EquivalenceCheck(entry, opts.bin, opts.work, opts.key4hep,
                                  opts.max_entries, opts.max_collections).run()
        reports.append(md)
        if not ok:
            rc = 1

    # Printed for the terminal, and appended to --summary for the CI job page.
    out = "\n".join(reports)
    print(out)
    if opts.summary:
        with open(opts.summary, "a") as fh:
            fh.write(out + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
