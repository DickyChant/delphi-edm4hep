#!/usr/bin/env python3
"""Unit checks for lolept94 payload/catalog event-count separation."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    inventory = load("audit_lolept94_event_inventory", "audit_lolept94_event_inventory.py")
    summary = load("summarize_lepton_pid_campaign", "summarize_lepton_pid_campaign.py")
    plotting = load("plot_lepton_pid_validation", "plot_lepton_pid_validation.py")

    assert inventory.EXPECTED_PAYLOAD_EVENTS == 831_002
    assert inventory.CATALOG_EVENTS == 828_851
    assert inventory.EXPECTED_PAYLOAD_EVENTS - inventory.CATALOG_EVENTS == 2_151
    assert summary.EXPECTED_EVENTS == inventory.EXPECTED_PAYLOAD_EVENTS
    assert summary.CATALOG_EVENTS == inventory.CATALOG_EVENTS
    assert plotting.EXPECTED_EVENTS == inventory.EXPECTED_PAYLOAD_EVENTS
    assert plotting.CATALOG_EVENTS == inventory.CATALOG_EVENTS

    validation = (
        "status=PASS entries=17 expected_run=data btag_mode=recalc "
        "recalculated_expected=1 frames_checked=17 failures=0 "
        "frame_read_failures=0 identity_failures=0"
    )
    assert inventory.parse_validation_entries(validation, "test") == 17
    try:
        inventory.parse_validation_entries(validation.replace("failures=0", "failures=1"), "test")
    except inventory.AuditError:
        pass
    else:
        raise AssertionError("failing validation summary was accepted")

    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        (directory / "one").write_text("1", encoding="utf-8")
        inventory.require_exact_names(directory, {"one"}, "fixture")
        try:
            inventory.require_exact_names(directory, {"two"}, "fixture")
        except inventory.AuditError:
            pass
        else:
            raise AssertionError("incorrect exact inventory was accepted")

    shell = (HERE / "batch_leptonic_long_94c.sh").read_text(encoding="utf-8")
    for assignment in (
        "EXPECTED_EVENTS=831002",
        "CATALOG_EVENTS=828851",
        "CATALOG_EVENT_DISCREPANCY=2151",
    ):
        assert assignment in shell
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
