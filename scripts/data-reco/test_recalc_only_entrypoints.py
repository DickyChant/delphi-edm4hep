#!/usr/bin/env python3
"""CLI regression checks for the recalculated-only production policy.

The rejected invocations fail before any campaign directory, input, container,
or converter is inspected, so this test never starts production work.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent


def reject(
    script: str,
    arguments: list[str],
    *,
    btag_mode: str | None = None,
    expected: str = "recalculated-AABTAG-only",
) -> None:
    environment = os.environ.copy()
    if btag_mode is None:
        environment.pop("BTAG_MODE", None)
    else:
        environment["BTAG_MODE"] = btag_mode
    completed = subprocess.run(
        ["bash", str(HERE / script), *arguments],
        cwd=HERE,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 2 or expected not in completed.stdout:
        raise AssertionError(
            f"{script} did not reject {arguments!r} with the production-policy "
            f"gate (exit={completed.returncode}):\n{completed.stdout}"
        )


def main() -> int:
    reject("batch_94c.sh", ["1", "1", "sdst"], btag_mode="bank")
    reject("batch_94c.sh", ["1", "1", "sdst"], btag_mode="off")
    reject("run_data_twopass.sh", ["missing.al", "missing.dst", "out", "1"], btag_mode="bank")
    reject("run_data_twopass.sh", ["missing.al", "missing.dst", "out", "1"], btag_mode="off")
    reject("batch_sdst_mc.sh", ["--btag-mode", "bank", "21000"])
    reject("batch_sdst_mc.sh", ["--btag-mode=off", "21000"])
    reject(
        "batch_sdst_mc.sh",
        [
            "--source-dir",
            "/tmp",
            "--output-dir",
            "/tmp/..",
            "--dry-run",
            "21000",
        ],
        expected="refusing to use / as the output directory",
    )
    reject(
        "batch_leptonic_long_94c.sh",
        ["--btag-mode", "bank"],
        expected="unknown argument: --btag-mode",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
