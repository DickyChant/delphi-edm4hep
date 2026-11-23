#!/usr/bin/env python3
"""Unit checks for the dual-prefix lepton completion-summary contract."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def summary(source: str) -> str:
    reference_schema = "source-local-v1" if source == "sDST" else "not-applicable"
    return (
        "status=PASS entries=17 expected_run=data "
        f"source={source} identity_source=sDST_EVT btag_mode=recalc "
        "recalculated_expected=1 provenance_schema=source-local-v1 "
        f"beamspot_status_source={source}_BTAGCFG_BeamSpotErrorCode "
        "legacy_fdst_beamspot_fallback_requested=0 "
        "legacy_fdst_beamspot_fallback_used=0 "
        f"reference_provenance_schema={reference_schema} "
        "legacy_reference_beamspot_fallback_requested=0 "
        "legacy_reference_beamspot_fallback_used=0 "
        "frames_checked=17 failures=0 identity_failures=0 mode_failures=0 "
        "recalculated_failures=0 missing_collections=0 "
        "validity_contract_failures=0"
    )


def frozen_v1_summary() -> str:
    return (
        "status=PASS entries=17 expected_run=data btag_mode=recalc "
        "recalculated_expected=1 frames_checked=17 failures=0 "
        "frame_read_failures=0 identity_failures=0 mode_failures=0 "
        "recalculated_failures=0 missing_collections=0 "
        "validity_contract_failures=0"
    )


def main() -> int:
    aggregate = load("summarize_lepton_pid_campaign", "summarize_lepton_pid_campaign.py")
    plotting = load("plot_lepton_pid_validation", "plot_lepton_pid_validation.py")
    for source in ("sDST", "fDST"):
        assert aggregate.parse_btag_summary(summary(source), source, "test")["entries"] == "17"
        assert plotting.parse_validation_summary(summary(source), source, "test")["entries"] == "17"
    for parser in (
        lambda: aggregate.parse_btag_summary(summary("sDST"), "fDST", "test"),
        lambda: plotting.parse_validation_summary(summary("sDST"), "fDST", "test"),
    ):
        try:
            parser()
        except RuntimeError:
            pass
        else:
            raise AssertionError("source-mismatched checker summary was accepted")
    assert aggregate.FROZEN_V1_CAMPAIGN_SHA256 == plotting.FROZEN_V1_CAMPAIGN_SHA256
    assert aggregate.parse_frozen_v1_btag_summary(
        frozen_v1_summary(), "test"
    )["entries"] == "17"
    assert plotting.parse_frozen_v1_validation_summary(
        frozen_v1_summary(), "test"
    )["entries"] == "17"
    for parser in (
        lambda: aggregate.parse_frozen_v1_btag_summary(
            frozen_v1_summary().replace("identity_failures=0", "identity_failures=1"),
            "test",
        ),
        lambda: plotting.parse_frozen_v1_validation_summary(
            frozen_v1_summary().replace("identity_failures=0", "identity_failures=1"),
            "test",
        ),
    ):
        try:
            parser()
        except RuntimeError:
            pass
        else:
            raise AssertionError("failing frozen-v1 checker summary was accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
