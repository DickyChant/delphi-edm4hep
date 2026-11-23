#!/usr/bin/env python3
"""Aggregate a completed lolept94_c2 campaign without rereading its ROOT files.

Every per-tape JSON report is already produced by ``audit_lepton_pid.py`` after
reading all events.  This program verifies that each report is bound by the
corresponding completion marker, checks the exact official 132-tape inventory,
and sums the physics-facing PID counters into one deterministic report.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence

from report_destination import (
    ReportDestinationError,
    atomic_write_report_text,
    lexical_absolute,
    validate_report_destination,
)


REPORT_FORMAT = "delphi-lolept94-c2-pid-campaign-summary-v1"
EXPECTED_DATASET = "lolept94_c2"
EXPECTED_FILES = 132
EXPECTED_EVENTS = 831_002
CATALOG_EVENTS = 828_851
CATALOG_EVENT_DISCREPANCY = EXPECTED_EVENTS - CATALOG_EVENTS
EXPECTED_INPUT_BYTES = 12_076_784_640
EXPECTED_MANIFEST_SHA256 = (
    "68096b0346f93f4952c5a119b7cfe28858882b6947a1da1f6773198add02c54b"
)
FROZEN_V1_CAMPAIGN_SHA256 = (
    "7e63c35ae3114881ffac931e2c111cfc455efaa18334b838e9095f083f9fa986"
)


class AuditError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_key_values(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        if "=" not in raw:
            raise AuditError(f"{path}:{line_number}: expected key=value")
        key, value = raw.split("=", 1)
        if not key or key in values:
            raise AuditError(f"{path}:{line_number}: empty or duplicate key {key!r}")
        values[key] = value
    return values


def parse_btag_summary(value: str, source: str, context: str) -> Dict[str, str]:
    try:
        tokens = shlex.split(value)
    except ValueError as exc:
        raise AuditError(f"{context}: malformed checker summary: {exc}") from exc
    parsed: Dict[str, str] = {}
    for token in tokens:
        key, separator, item = token.partition("=")
        if not separator or not key or key in parsed:
            raise AuditError(f"{context}: malformed checker token {token!r}")
        parsed[key] = item
    expected = {
        "status": "PASS",
        "source": source,
        "identity_source": "sDST_EVT",
        "btag_mode": "recalc",
        "recalculated_expected": "1",
        "provenance_schema": "source-local-v1",
        "beamspot_status_source": f"{source}_BTAGCFG_BeamSpotErrorCode",
        "legacy_fdst_beamspot_fallback_requested": "0",
        "legacy_fdst_beamspot_fallback_used": "0",
        "reference_provenance_schema": (
            "source-local-v1" if source == "sDST" else "not-applicable"
        ),
        "legacy_reference_beamspot_fallback_requested": "0",
        "legacy_reference_beamspot_fallback_used": "0",
        "failures": "0",
    }
    for key, wanted in expected.items():
        if parsed.get(key) != wanted:
            raise AuditError(
                f"{context}: {key}={parsed.get(key)!r}, expected {wanted!r}"
            )
    return parsed


def parse_frozen_v1_btag_summary(value: str, context: str) -> Dict[str, str]:
    """Parse only the checker schema bound to the exact frozen v1 campaign."""
    try:
        tokens = shlex.split(value)
    except ValueError as exc:
        raise AuditError(f"{context}: malformed frozen checker summary: {exc}") from exc
    parsed: Dict[str, str] = {}
    for token in tokens:
        key, separator, item = token.partition("=")
        if not separator or not key or key in parsed:
            raise AuditError(f"{context}: malformed frozen checker token {token!r}")
        parsed[key] = item
    expected = {
        "status": "PASS",
        "expected_run": "data",
        "btag_mode": "recalc",
        "recalculated_expected": "1",
        "failures": "0",
        "frame_read_failures": "0",
        "identity_failures": "0",
        "mode_failures": "0",
        "recalculated_failures": "0",
        "missing_collections": "0",
        "validity_contract_failures": "0",
    }
    for key, wanted in expected.items():
        if parsed.get(key) != wanted:
            raise AuditError(
                f"{context}: {key}={parsed.get(key)!r}, expected {wanted!r}"
            )
    return parsed


def require_regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise AuditError(f"required regular file is missing: {path}")
    if path.stat().st_size <= 0:
        raise AuditError(f"required file is empty: {path}")


def integer(value: Any, context: str, *, positive: bool = False) -> int:
    if isinstance(value, bool):
        raise AuditError(f"{context}: boolean is not an integer count")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise AuditError(f"{context}: invalid integer {value!r}") from exc
    if str(result) != str(value):
        raise AuditError(f"{context}: non-canonical integer {value!r}")
    if result < 0 or (positive and result == 0):
        qualifier = "positive" if positive else "nonnegative"
        raise AuditError(f"{context}: expected {qualifier} integer, got {result}")
    return result


def add_counter(
    destination: MutableMapping[str, int], source: Mapping[str, Any], context: str
) -> None:
    if not isinstance(source, Mapping):
        raise AuditError(f"{context}: expected an object")
    for key, value in source.items():
        destination[str(key)] = destination.get(str(key), 0) + integer(
            value, f"{context}.{key}"
        )


def new_aggregate() -> Dict[str, Any]:
    return {
        "events": 0,
        "particles": 0,
        "collection_rows": {},
        "particle_id_contract": {},
        "muon_id": {"raw_tag_distribution": {}, "set_bit_counts": {}},
        "electron_id": {
            "tag_distribution": {},
            "conversion_tag_distribution": {},
            "tag_by_conversion_distribution": {},
            "conversion_veto_rows": 0,
            "standard_or_tighter_rows": 0,
            "standard_or_tighter_conversion_veto_rows": 0,
            "undocumented_tag_outside_1_to_5_rows": 0,
            "undocumented_conversion_tag_outside_0_to_3_rows": 0,
        },
        "target_response": {
            "dedx": {},
            "rich_gas": {"flag_distribution": {}},
            "rich_liquid": {"flag_distribution": {}},
        },
        "opposite_sign_high_momentum_diagnostics": {
            "minimum_momentum_gev_per_particle": None,
            "categories": {},
        },
    }


def merge_summary(aggregate: Dict[str, Any], summary: Mapping[str, Any], context: str) -> None:
    aggregate["events"] += integer(summary.get("events"), f"{context}.events")
    aggregate["particles"] += integer(summary.get("particles"), f"{context}.particles")
    add_counter(aggregate["collection_rows"], summary.get("collection_rows"), f"{context}.collection_rows")
    add_counter(
        aggregate["particle_id_contract"],
        summary.get("particle_id_contract"),
        f"{context}.particle_id_contract",
    )

    muon = summary.get("muon_id")
    if not isinstance(muon, Mapping):
        raise AuditError(f"{context}.muon_id: expected an object")
    for key in ("raw_tag_distribution", "set_bit_counts"):
        add_counter(aggregate["muon_id"][key], muon.get(key), f"{context}.muon_id.{key}")

    electron = summary.get("electron_id")
    if not isinstance(electron, Mapping):
        raise AuditError(f"{context}.electron_id: expected an object")
    for key in (
        "tag_distribution",
        "conversion_tag_distribution",
        "tag_by_conversion_distribution",
    ):
        add_counter(
            aggregate["electron_id"][key],
            electron.get(key),
            f"{context}.electron_id.{key}",
        )
    for key in (
        "conversion_veto_rows",
        "standard_or_tighter_rows",
        "standard_or_tighter_conversion_veto_rows",
        "undocumented_tag_outside_1_to_5_rows",
        "undocumented_conversion_tag_outside_0_to_3_rows",
    ):
        aggregate["electron_id"][key] += integer(
            electron.get(key), f"{context}.electron_id.{key}"
        )

    target = summary.get("target_response")
    if not isinstance(target, Mapping):
        raise AuditError(f"{context}.target_response: expected an object")
    add_counter(
        aggregate["target_response"]["dedx"],
        target.get("dedx"),
        f"{context}.target_response.dedx",
    )
    for radiator in ("rich_gas", "rich_liquid"):
        values = target.get(radiator)
        if not isinstance(values, Mapping):
            raise AuditError(f"{context}.target_response.{radiator}: expected an object")
        flags = values.get("flag_distribution")
        add_counter(
            aggregate["target_response"][radiator]["flag_distribution"],
            flags,
            f"{context}.target_response.{radiator}.flag_distribution",
        )
        add_counter(
            aggregate["target_response"][radiator],
            {key: value for key, value in values.items() if key != "flag_distribution"},
            f"{context}.target_response.{radiator}",
        )

    pairs = summary.get("opposite_sign_high_momentum_diagnostics")
    if not isinstance(pairs, Mapping):
        raise AuditError(
            f"{context}.opposite_sign_high_momentum_diagnostics: expected an object"
        )
    threshold = pairs.get("minimum_momentum_gev_per_particle")
    stored = aggregate["opposite_sign_high_momentum_diagnostics"][
        "minimum_momentum_gev_per_particle"
    ]
    if stored is None:
        aggregate["opposite_sign_high_momentum_diagnostics"][
            "minimum_momentum_gev_per_particle"
        ] = threshold
    elif threshold != stored:
        raise AuditError(f"{context}: inconsistent high-momentum threshold")
    categories = pairs.get("categories")
    if not isinstance(categories, Mapping):
        raise AuditError(f"{context}: pair categories are not an object")
    destination = aggregate["opposite_sign_high_momentum_diagnostics"]["categories"]
    for name, counts in categories.items():
        if name not in destination:
            destination[name] = {"pairs": 0, "events_with_at_least_one_pair": 0}
        add_counter(destination[name], counts, f"{context}.categories.{name}")


def read_manifest(path: Path) -> Sequence[tuple[str, int]]:
    rows = []
    for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = raw.split("\t")
        expected = f"Y13718.{index}.al"
        if len(fields) != 2 or fields[0] != expected:
            raise AuditError(f"{path}:{index}: expected exact row for {expected}")
        rows.append((fields[0][:-3], integer(fields[1], f"{path}:{index}", positive=True)))
    if len(rows) != EXPECTED_FILES:
        raise AuditError(f"manifest has {len(rows)} rows, expected {EXPECTED_FILES}")
    if sum(size for _, size in rows) != EXPECTED_INPUT_BYTES:
        raise AuditError("manifest input-byte total differs from the official record")
    return rows


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def write_json_atomic(path: Path, report: Mapping[str, Any]) -> None:
    payload = json.dumps(canonicalize(dict(report)), indent=2, allow_nan=False) + "\n"
    atomic_write_report_text(path, payload)


def summarize(campaign: Path) -> Dict[str, Any]:
    campaign = campaign.resolve(strict=True)
    if not campaign.is_dir():
        raise AuditError(f"campaign is not a directory: {campaign}")
    config_path = campaign / "campaign.conf"
    manifest_path = campaign / "inputs.manifest.tsv"
    require_regular(config_path)
    require_regular(manifest_path)
    if sha256(manifest_path) != EXPECTED_MANIFEST_SHA256:
        raise AuditError("campaign manifest SHA-256 differs from the audited inventory")
    config = load_key_values(config_path)
    campaign_sha = sha256(config_path)
    frozen_v1 = campaign_sha == FROZEN_V1_CAMPAIGN_SHA256
    expected_config = {
        "format": (
            "delphi-lolept94-c2-recalc-v1"
            if frozen_v1
            else "delphi-lolept94-c2-recalc-v2"
        ),
        "dataset": EXPECTED_DATASET,
        "btag_mode": "recalc",
        "recalculated": "1",
        "file_count": str(EXPECTED_FILES),
        "input_bytes": str(EXPECTED_INPUT_BYTES),
        "expected_events": str(CATALOG_EVENTS if frozen_v1 else EXPECTED_EVENTS),
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
    }
    if not frozen_v1:
        expected_config.update(
            {
                "catalog_events": str(CATALOG_EVENTS),
                "catalog_event_discrepancy": str(CATALOG_EVENT_DISCREPANCY),
            }
        )
    for key, value in expected_config.items():
        if config.get(key) != value:
            raise AuditError(f"campaign.conf {key}={config.get(key)!r}, expected {value!r}")

    aggregate = new_aggregate()
    files = []
    total_root_bytes = 0
    for tape, input_size in read_manifest(manifest_path):
        root = campaign / "edm4hep" / f"lolept94_c2_{tape}.edm4hep.root"
        marker_path = Path(f"{root}.complete")
        audit_path = campaign / "audits" / f"{tape}.lepton_pid.json"
        for path in (root, marker_path, audit_path):
            require_regular(path)

        marker = load_key_values(marker_path)
        root_sha = sha256(root)
        expected_marker = {
            "format": (
                "delphi-lolept94-c2-complete-v1"
                if frozen_v1
                else "delphi-lolept94-c2-complete-v2"
            ),
            "phase": "final",
            "tape": tape,
            "input_size_bytes": str(input_size),
            "output": root.name,
            "output_size_bytes": str(root.stat().st_size),
            "btag_mode": "recalc",
            "recalculated": "1",
            "identity_check": "exact-ordered-run-event-fileSeq",
            "campaign_sha256": campaign_sha,
            "auditor_sha256": config.get("auditor_sha256"),
            "checker_sha256": config.get("checker_sha256"),
            "lepton_schema_audit_sha256": sha256(audit_path),
        }
        if not frozen_v1:
            expected_marker["output_sha256"] = root_sha
        for key, value in expected_marker.items():
            if marker.get(key) != value:
                raise AuditError(f"{marker_path}: {key}={marker.get(key)!r}, expected {value!r}")
        events = integer(marker.get("events"), f"{marker_path}:events", positive=True)
        if frozen_v1:
            validation = parse_frozen_v1_btag_summary(
                marker.get("validation", ""), f"{marker_path}:validation"
            )
            if integer(
                validation.get("entries"),
                f"{marker_path}:validation.entries",
                positive=True,
            ) != events:
                raise AuditError(f"{marker_path}: frozen checker count differs")
        else:
            for source, key in (
                ("sDST", "sdst_validation"),
                ("fDST", "fdst_validation"),
            ):
                validation = parse_btag_summary(
                    marker.get(key, ""), source, f"{marker_path}:{key}"
                )
                if integer(
                    validation.get("entries"),
                    f"{marker_path}:{key}.entries",
                    positive=True,
                ) != events:
                    raise AuditError(f"{marker_path}: {source} checker count differs")

        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuditError(f"cannot decode {audit_path}: {exc}") from exc
        if audit.get("format") != "delphi-edm4hep-lepton-pid-audit-v1":
            raise AuditError(f"{audit_path}: unexpected report format")
        if audit.get("status") != "PASS" or audit.get("failures", {}).get("count") != 0:
            raise AuditError(f"{audit_path}: lepton PID audit is not PASS with zero failures")
        inputs = audit.get("inputs")
        if not isinstance(inputs, Mapping) or inputs.get("file_count") != 1:
            raise AuditError(f"{audit_path}: expected exactly one audited input")
        if inputs.get("total_size_bytes") != root.stat().st_size:
            raise AuditError(f"{audit_path}: audited byte count differs from ROOT file")
        input_files = inputs.get("files")
        if not isinstance(input_files, list) or len(input_files) != 1:
            raise AuditError(f"{audit_path}: malformed audited input list")
        audited_input = Path(input_files[0])
        # A newly produced file is audited under its unique temporary name and
        # then atomically renamed.  A resumed file is audited under the final
        # name.  Accept precisely those two cases, in the same final directory.
        temporary_prefix = f".lolept94_c2_{tape}."
        audited_name_ok = (
            audited_input.resolve() == root.resolve()
            or (
                audited_input.parent.resolve() == root.parent.resolve()
                and audited_input.name.startswith(temporary_prefix)
                and audited_input.name.endswith(".tmp.root")
                and len(audited_input.name)
                == len(temporary_prefix) + 6 + len(".tmp.root")
            )
        )
        if not audited_name_ok:
            raise AuditError(f"{audit_path}: audited input path is not the atomic source of the ROOT file")
        summary = audit.get("summary")
        if not isinstance(summary, Mapping):
            raise AuditError(f"{audit_path}: missing summary object")
        if integer(summary.get("events"), f"{audit_path}:summary.events") != events:
            raise AuditError(f"{audit_path}: event count differs from completion marker")
        merge_summary(aggregate, summary, str(audit_path))
        total_root_bytes += root.stat().st_size
        files.append(
            {
                "tape": tape,
                "events": events,
                "root": str(root),
                "root_size_bytes": root.stat().st_size,
                "root_sha256": root_sha,
                "completion_marker": str(marker_path),
                "audit": str(audit_path),
                "audit_sha256": sha256(audit_path),
            }
        )

    if aggregate["events"] != EXPECTED_EVENTS:
        raise AuditError(
            f"aggregate has {aggregate['events']} events, expected {EXPECTED_EVENTS}"
        )
    relations = aggregate["particle_id_contract"]
    if relations.get("relations_checked") != relations.get("relations_valid"):
        raise AuditError("aggregate has invalid ParticleID relations")
    return {
        "format": REPORT_FORMAT,
        "status": "PASS",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "dataset": EXPECTED_DATASET,
        "production_policy": {
            "btag_mode": "recalc",
            "recalculated": True,
            "bank_production": "retired",
            "btag_provenance_schema": (
                "legacy-frozen-v1" if frozen_v1 else "source-local-v1"
            ),
            "identity_source": "sDST_EVT",
            "input_contract": (
                "exact-frozen-v1-campaign-sha256" if frozen_v1 else "current-v2"
            ),
        },
        "inventory": {
            "file_count": len(files),
            "event_count": aggregate["events"],
            "catalog_event_count": CATALOG_EVENTS,
            "catalog_event_discrepancy": CATALOG_EVENT_DISCREPANCY,
            "catalog_event_count_role": "metadata-not-payload-acceptance",
            "input_long_dst_bytes": EXPECTED_INPUT_BYTES,
            "output_edm4hep_bytes": total_root_bytes,
            "manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "campaign_config_sha256": campaign_sha,
        },
        "summary": aggregate,
        "files": files,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path, help="completed lolept94_c2 campaign directory")
    parser.add_argument("--output", type=Path, help="summary JSON (default: CAMPAIGN/lepton_pid_campaign_summary.json)")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    campaign = args.campaign.expanduser().resolve(strict=False)
    reserved_output = campaign / "lepton_pid_campaign_summary.json"
    supplemental_output = (
        campaign / "supplemental_reports" / "lepton_pid_campaign_summary.json"
    )
    requested_output = lexical_absolute(args.output or reserved_output)
    try:
        output = validate_report_destination(
            requested_output,
            protected_files=(Path(__file__).resolve(),),
            root_policies=((campaign, (reserved_output, supplemental_output)),),
        )
    except ReportDestinationError as exc:
        print(f"ERROR: unsafe summary destination: {exc}", file=sys.stderr)
        return 2
    try:
        report = summarize(campaign)
    except (AuditError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    try:
        write_json_atomic(output, report)
    except (OSError, ReportDestinationError) as exc:
        print(f"ERROR: could not write summary atomically: {exc}", file=sys.stderr)
        return 2
    digest = sha256(output)
    print(
        f"status=PASS dataset={EXPECTED_DATASET} files={report['inventory']['file_count']} "
        f"events={report['inventory']['event_count']} summary_sha256={digest} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
