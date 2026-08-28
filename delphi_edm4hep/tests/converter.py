#!/usr/bin/env python3
"""Invoke delphi_sdst_pass for one sample selector.

Selectors come from samples.yaml as {mode, value}:

    nickname   -N <value>    fatfind dataset
    pdl        -P <value>    pre-expanded PDL file
    file       <value>       explicit path

Command line is <bin> <selector> <output> [-n N]; max_events of -1 means the
whole file.
"""
import subprocess
from pathlib import Path

# PHDST truncates its input path at this length and then opens nothing,
# reporting "error in CFOPEN" and processing zero files.
MAX_INPUT_PATH = 120

OUTPUT_NAME = "out.edm4hep.root"
LOG_NAME = "convert.log"


class Conversion:
    """Result of one converter invocation."""

    def __init__(self, returncode, workdir, message=None):
        self.returncode = returncode
        self.workdir = Path(workdir)
        self.message = message

    @property
    def ok(self):
        return self.returncode == 0

    @property
    def root(self):
        return self.workdir / OUTPUT_NAME

    @property
    def log(self):
        return self.workdir / LOG_NAME

    @property
    def pdlinput(self):
        return self.workdir / "PDLINPUT"


def argv(binary, selector, output=OUTPUT_NAME, max_events=-1):
    """Command line for one selector."""
    mode, value = selector["mode"], selector["value"]
    sel = {"nickname": ["-N", value],
           "pdl": ["-P", value],
           "file": [value]}.get(mode)
    if sel is None:
        raise ValueError(f"unknown select.mode {mode!r}")
    line = [str(binary), *sel, output]
    if max_events > 0:
        line += ["-n", str(max_events)]
    return line


def run(binary, selector, workdir, max_events=-1):
    """Convert into workdir and return a Conversion.

    The converter runs with workdir as its working directory, since the harness
    writes PDLINPUT there. Output and log are named by OUTPUT_NAME / LOG_NAME.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    if selector["mode"] == "file" and len(selector["value"]) > MAX_INPUT_PATH:
        return Conversion(1, workdir,
                          f"input path is {len(selector['value'])} characters, "
                          f"over the {MAX_INPUT_PATH} PHDST accepts")

    try:
        line = argv(binary, selector, OUTPUT_NAME, max_events)
    except ValueError as e:
        return Conversion(1, workdir, str(e))

    with open(workdir / LOG_NAME, "w") as fh:
        rc = subprocess.call(line, cwd=workdir, stdout=fh, stderr=subprocess.STDOUT)
    if rc != 0:
        return Conversion(rc, workdir, f"converter exited {rc}")
    return Conversion(0, workdir)
