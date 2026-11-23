#!/usr/bin/env python3
"""Audit the complete official DELPHI v94c qqps 91.25 GeV MC campaign.

The batch driver publishes an output only after ``delphi_btag_check`` has
scanned every event.  This script treats that checker's stable key=value line
as the ROOT/podio entry count, cross-checks it against the converter log and
completion marker, and aggregates the complete 166-file campaign.

The CERN Open Data record advertises 488472 events.  The authoritative sum of
the payloads in its 166 indexed SDST files is 488468; that known four-event
catalogue discrepancy is recorded explicitly and is not silently papered over.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable, Sequence

from report_destination import (
    ReportDestinationError,
    atomic_write_report_text,
    lexical_absolute,
    validate_report_destination,
)


OFFICIAL_IDS = tuple(range(21000, 21091)) + tuple(range(21092, 21167))
OFFICIAL_FILE_COUNT = 166
PAYLOAD_EVENT_COUNT = 488_468
CATALOGUE_EVENT_COUNT = 488_472
CATALOGUE_RECORD = {
    "record_id": 81437,
    "url": "https://opendata.cern.ch/record/81437",
    "doi": "10.7483/OPENDATA.DELPHI.0HML.4DOT",
    "title": "sh_qqps_e91.25_c94_2l_c2",
    "origin": "CERN",
    "indexed_sdst_files": OFFICIAL_FILE_COUNT,
    "metadata_events": CATALOGUE_EVENT_COUNT,
}
DEFAULT_SOURCE_DIR = Path(
    "/eos/opendata/delphi/simulated-data/cern/qqps/v94c/91.25"
)
CALIBRATION_FILE = "P94C2FMC.610"

CHECKER_KEYS = {
    "status",
    "entries",
    "expected_run",
    "source",
    "identity_source",
    "btag_mode",
    "recalculated_expected",
    "chi2_pv_contract",
    "chi2_pv_roundoff_tolerance",
    "provenance_schema",
    "beamspot_status_source",
    "primary_vertex_policy",
    "primary_vertex_policy_expected",
    "iflpvt",
    "legacy_fdst_beamspot_fallback_requested",
    "legacy_fdst_beamspot_fallback_used",
    "frames_checked",
    "failures",
    "frame_read_failures",
    "run_failures",
    "identity_reference",
    "reference_provenance_schema",
    "legacy_reference_beamspot_fallback_requested",
    "legacy_reference_beamspot_fallback_used",
    "reference_entries",
    "reference_entry_count_failures",
    "reference_frame_read_failures",
    "reference_source_local_provenance_frames",
    "legacy_reference_fallback_frames",
    "identity_failures",
    "mode_failures",
    "recalculated_failures",
    "provenance_failures",
    "primary_vertex_policy_failures",
    "source_local_provenance_frames",
    "legacy_sdst_provenance_frames",
    "legacy_fdst_fallback_frames",
    "missing_event_parameters",
    "off_payload_presence_failures",
    "bank_payload_empty_failures",
    "event_vector_length_failures",
    "event_probability_nans",
    "event_probability_range_failures",
    "thrust_nans",
    "thrust_range_failures",
    "missing_track_parameters",
    "missing_collections",
    "track_vector_length_failures",
    "track_probability_nonfinite_failures",
    "track_probability_range_failures",
    "track_impact_nonfinite_failures",
    "track_error_domain_failures",
    "track_chi2_domain_failures",
    "track_chi2_pv_roundoff_values",
    "track_chi2_pv_undefined_values",
    "track_momentum_domain_failures",
    "track_integer_domain_failures",
    "pv_size_failures",
    "pv_primary_flag_failures",
    "pv_algorithm_type_failures",
    "pv_nonfinite_failures",
    "pv_ndf_domain_failures",
    "tracks",
    "unresolved_particle_indices",
    "particle_index_range_failures",
    "truncated_events",
    "bad_status_events",
    "beamspot_error_events",
    "aabtag_not_invoked_events",
    "aabtag_invalid_events",
    "validity_contract_failures",
    "truncation_failures",
    "attached_consistency_failures",
}
OPTIONAL_CHECKER_KEYS: set[str] = set()

CHECKER_INTEGER_KEYS = (CHECKER_KEYS | OPTIONAL_CHECKER_KEYS) - {
    "status",
    "source",
    "identity_source",
    "btag_mode",
    "chi2_pv_contract",
    "chi2_pv_roundoff_tolerance",
    "provenance_schema",
    "beamspot_status_source",
    "primary_vertex_policy",
    "primary_vertex_policy_expected",
    "identity_reference",
    "reference_provenance_schema",
}

REQUIRED_ZERO_COUNTERS = (
    "failures",
    "frame_read_failures",
    "run_failures",
    "reference_entry_count_failures",
    "reference_frame_read_failures",
    "identity_failures",
    "mode_failures",
    "recalculated_failures",
    "provenance_failures",
    "primary_vertex_policy_failures",
    "missing_event_parameters",
    "off_payload_presence_failures",
    "bank_payload_empty_failures",
    "event_vector_length_failures",
    "event_probability_range_failures",
    "thrust_range_failures",
    "missing_track_parameters",
    "missing_collections",
    "track_vector_length_failures",
    "track_probability_nonfinite_failures",
    "track_probability_range_failures",
    "track_impact_nonfinite_failures",
    "track_error_domain_failures",
    "track_chi2_domain_failures",
    "track_momentum_domain_failures",
    "track_integer_domain_failures",
    "pv_size_failures",
    "pv_primary_flag_failures",
    "pv_algorithm_type_failures",
    "pv_nonfinite_failures",
    "pv_ndf_domain_failures",
    "particle_index_range_failures",
    "validity_contract_failures",
    "truncation_failures",
    "attached_consistency_failures",
)

DIAGNOSTIC_COUNTERS = (
    "event_probability_nans",
    "thrust_nans",
    "bad_status_events",
    "beamspot_error_events",
    "aabtag_not_invoked_events",
    "aabtag_invalid_events",
    "tracks",
    "track_chi2_pv_roundoff_values",
    "track_chi2_pv_undefined_values",
    "unresolved_particle_indices",
    "truncated_events",
)

WRITTEN_RE = re.compile(
    r"delphi_edm4hep::harness:\s+wrote\s+(\d+)\s+events\b"
)
CALIBRATION_RE = re.compile(
    r"AAOPEN\s+-\s+Open file of type\s+MC:(P94C2FMC\.[A-Za-z0-9]+)"
)
ROOT_RE = re.compile(r"qqps_91\.25_(\d+)\.edm4hep\.root$")
MARKER_RE = re.compile(r"qqps_91\.25_(\d+)\.edm4hep\.root\.complete$")
CONVERTER_LOG_RE = re.compile(r"qqps_91\.25_(\d+)\.log$")
CHECKER_LOG_RE = re.compile(
    r"qqps_91\.25_(\d+)\.(recalc)\.validation\.log$"
)
SOURCE_RE = re.compile(r"qqps_91\.25_(\d+)\.sdst$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def digest_rows(rows: Iterable[str]) -> str:
    encoded = "".join(f"{row}\n" for row in rows).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_key_values(line: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in shlex.split(line, posix=True):
        if "=" not in token:
            raise ValueError(f"token has no '=': {token!r}")
        key, value = token.split("=", 1)
        if not key or key in result:
            raise ValueError(f"empty or duplicate key: {key!r}")
        result[key] = value
    return result


def parse_checker_log(path: Path) -> tuple[str, dict[str, Any]]:
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip().startswith("status=")
    ]
    if len(lines) != 1:
        raise ValueError(f"expected one checker summary, found {len(lines)}")
    raw = lines[0]
    values: dict[str, Any] = parse_key_values(raw)
    missing = sorted(CHECKER_KEYS - values.keys())
    extra = sorted(values.keys() - (CHECKER_KEYS | OPTIONAL_CHECKER_KEYS))
    if missing or extra:
        raise ValueError(f"checker schema mismatch: missing={missing}, extra={extra}")
    for key in CHECKER_INTEGER_KEYS & values.keys():
        try:
            values[key] = int(values[key])
        except ValueError as error:
            raise ValueError(f"checker field {key!r} is not an integer") from error
    return raw, values


def parse_marker(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for number, raw in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        if not raw or "=" not in raw:
            raise ValueError(f"invalid marker line {number}: {raw!r}")
        key, value = raw.split("=", 1)
        if not key or key in result:
            raise ValueError(f"empty or duplicate marker key on line {number}")
        result[key] = value
    return result


def git_head(repo: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def matching_ids(directory: Path, regex: re.Pattern[str]) -> tuple[set[int], list[str]]:
    ids: set[int] = set()
    duplicates: list[str] = []
    if not directory.is_dir():
        return ids, duplicates
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        match = regex.fullmatch(path.name)
        if not match:
            continue
        file_id = int(match.group(1))
        if file_id in ids:
            duplicates.append(path.name)
        ids.add(file_id)
    return ids, duplicates


def sorted_relative(paths: Iterable[Path], base: Path) -> list[str]:
    return sorted(str(path.relative_to(base)) for path in paths)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    atomic_write_report_text(path, rendered)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_checker_summary(
    checker: dict[str, Any], file_id: int, mode: str
) -> list[str]:
    """Return semantic failures for one direct checker invocation."""

    expected_recalculated = 1 if mode == "recalc" else 0
    errors: list[str] = []
    expected = {
        "status": "PASS",
        "expected_run": -file_id,
        "source": "sDST",
        "identity_source": "sDST_EVT",
        "btag_mode": mode,
        "recalculated_expected": expected_recalculated,
        "chi2_pv_contract": "attached-only-v1",
        "chi2_pv_roundoff_tolerance": "0.25",
        "provenance_schema": "source-local-v1",
        "beamspot_status_source": "sDST_BTAGCFG_BeamSpotErrorCode",
        "primary_vertex_policy": "keep-delana",
        "primary_vertex_policy_expected": "keep-delana",
        "iflpvt": 0,
        "legacy_fdst_beamspot_fallback_requested": 0,
        "legacy_fdst_beamspot_fallback_used": 0,
        "identity_reference": "none",
        "reference_provenance_schema": "not-applicable",
        "legacy_reference_beamspot_fallback_requested": 0,
        "legacy_reference_beamspot_fallback_used": 0,
        "reference_entries": 0,
        "reference_source_local_provenance_frames": 0,
        "legacy_reference_fallback_frames": 0,
    }
    for key, value in expected.items():
        if checker[key] != value:
            errors.append(f"{key}: expected {value!r}, got {checker[key]!r}")
    if checker["entries"] != checker["frames_checked"]:
        errors.append(
            "entries/frames_checked mismatch: "
            f"{checker['entries']} != {checker['frames_checked']}"
        )
    if checker["source_local_provenance_frames"] != checker["entries"]:
        errors.append("source_local_provenance_frames differs from entries")
    if checker["legacy_sdst_provenance_frames"] != 0 or checker[
        "legacy_fdst_fallback_frames"
    ] != 0:
        errors.append("current output used legacy provenance")
    for key in REQUIRED_ZERO_COUNTERS:
        if checker[key] != 0:
            errors.append(f"{key}: expected 0, got {checker[key]}")
    if mode == "recalc":
        if checker["aabtag_not_invoked_events"] != checker["beamspot_error_events"]:
            errors.append(
                "aabtag_not_invoked_events differs from beamspot_error_events"
            )
        expected_invalid = (
            checker["aabtag_not_invoked_events"] + checker["bad_status_events"]
        )
        if checker["aabtag_invalid_events"] != expected_invalid:
            errors.append(
                "aabtag_invalid_events differs from not-invoked + bad-status"
            )
        if checker["event_probability_nans"] != 9 * expected_invalid:
            errors.append("event_probability_nans is not 9 per invalid event")
        if checker["thrust_nans"] != 4 * expected_invalid:
            errors.append("thrust_nans is not 4 per invalid event")
    return errors


def refresh_checker_evidence(
    *,
    campaign: Path,
    source_dir: Path,
    logs_dir: Path,
    mode: str,
    checker_executable: Path,
    workers: int,
) -> dict[str, Any]:
    """Scan existing ROOT files and atomically refresh validation metadata.

    This function never invokes ``delphi_sdst_pass`` and never opens an output
    for writing.  It publishes no metadata unless all 166 checker scans pass,
    their entry counts agree with the immutable converter logs, and every ROOT
    stat tuple is unchanged before/after the scan.
    """

    if not checker_executable.is_file() or not os.access(checker_executable, os.X_OK):
        raise RuntimeError(f"checker is not executable: {checker_executable}")

    required_roots = [
        campaign / f"qqps_91.25_{file_id}.edm4hep.root"
        for file_id in OFFICIAL_IDS
    ]
    required_logs = [
        logs_dir / f"qqps_91.25_{file_id}.log" for file_id in OFFICIAL_IDS
    ]
    for path in (*required_roots, *required_logs):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"required regular file is missing: {path}")

    active_temporaries = sorted(
        str(path.relative_to(campaign))
        for path in campaign.rglob("*")
        if path.name.endswith(".tmp.root") or ".tmp." in path.name
    )
    scratch_dir = campaign / ".scratch"
    active_scratch = (
        sorted(str(path.relative_to(campaign)) for path in scratch_dir.rglob("*"))
        if scratch_dir.is_dir()
        else []
    )
    if active_temporaries or active_scratch:
        raise RuntimeError(
            "campaign may still be active: "
            f"temporaries={active_temporaries}, scratch={active_scratch}"
        )

    checker_sha256 = sha256_file(checker_executable)

    def scan(file_id: int) -> dict[str, Any]:
        root = campaign / f"qqps_91.25_{file_id}.edm4hep.root"
        converter_log = logs_dir / f"qqps_91.25_{file_id}.log"
        before = root.stat()
        completed = subprocess.run(
            [
                str(checker_executable),
                "--source",
                "sDST",
                "--primary-vertex-policy",
                "keep-delana",
                str(root),
                str(-file_id),
                mode,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        after = root.stat()
        before_fingerprint = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        after_fingerprint = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        errors: list[str] = []
        if completed.returncode != 0:
            errors.append(f"checker exit code {completed.returncode}")
        if before_fingerprint != after_fingerprint:
            errors.append(
                f"ROOT stat changed: before={before_fingerprint}, "
                f"after={after_fingerprint}"
            )

        raw_summary: str | None = None
        checker: dict[str, Any] | None = None
        with tempfile.TemporaryDirectory(prefix="delphi_mc_check_parse_") as temporary:
            captured = Path(temporary) / "checker.log"
            captured.write_text(completed.stdout, encoding="utf-8")
            try:
                raw_summary, checker = parse_checker_log(captured)
            except (OSError, ValueError) as error:
                errors.append(f"checker output parse: {error}")
        if checker is not None:
            errors.extend(validate_checker_summary(checker, file_id, mode))

            converter_text = converter_log.read_text(
                encoding="utf-8", errors="replace"
            )
            written = [int(value) for value in WRITTEN_RE.findall(converter_text)]
            if written != [checker["entries"]]:
                errors.append(
                    f"converter/checker entries mismatch: {written} != "
                    f"[{checker['entries']}]"
                )

        return {
            "id": file_id,
            "output": completed.stdout,
            "summary": raw_summary,
            "checker": checker,
            "size_bytes": after.st_size,
            "stat_fingerprint": after_fingerprint,
            "errors": errors,
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        scans = list(executor.map(scan, OFFICIAL_IDS))

    failed = [
        {"id": item["id"], "errors": item["errors"]}
        for item in scans
        if item["errors"]
    ]
    if failed:
        raise RuntimeError(
            "direct checker refresh failed; no metadata was changed: "
            + json.dumps(failed, sort_keys=True)
        )

    event_total = sum(item["checker"]["entries"] for item in scans)
    if event_total != PAYLOAD_EVENT_COUNT:
        raise RuntimeError(
            "direct checker refresh found unexpected payload total; "
            f"no metadata was changed: {event_total} != {PAYLOAD_EVENT_COUNT}"
        )

    validated_utc = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    recalculated = 1 if mode == "recalc" else 0
    for item in scans:
        file_id = item["id"]
        stem = f"qqps_91.25_{file_id}"
        source = source_dir / f"{stem}.sdst"
        checker_log = logs_dir / f"{stem}.{mode}.validation.log"
        marker = campaign / f"{stem}.edm4hep.root.complete"
        checker_output = item["output"]
        if checker_output and not checker_output.endswith("\n"):
            checker_output += "\n"
        atomic_write_text(checker_log, checker_output)
        marker_text = "".join(
            (
                f"input={source}\n",
                f"run={-file_id}\n",
                f"btag_mode={mode}\n",
                "source=sDST\n",
                f"recalculated={recalculated}\n",
                "primary_vertex_policy=keep-delana\n",
                "iflpvt=0\n",
                f"size_bytes={item['size_bytes']}\n",
                f"validated_utc={validated_utc}\n",
                "validation_method=direct_delphi_btag_check\n",
                f"checker_sha256={checker_sha256}\n",
                f"validation={item['summary']}\n",
            )
        )
        atomic_write_text(marker, marker_text)

    return {
        "method": "direct_delphi_btag_check_only",
        "converter_invoked": False,
        "files_scanned": len(scans),
        "events_scanned": event_total,
        "checker_executable": str(checker_executable),
        "checker_sha256": checker_sha256,
        "validated_utc": validated_utc,
        "root_stat_unchanged": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_dir", type=Path)
    parser.add_argument(
        "--mode",
        choices=("recalc",),
        required=True,
        help=(
            "current production audit mode (stored-bank campaign evidence is "
            "historical and is not refreshable through this entrypoint)"
        ),
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--hash-workers",
        type=int,
        default=4,
        help="parallel workers for SHA-256 calculation (default: 4)",
    )
    parser.add_argument(
        "--refresh-checker-evidence",
        action="store_true",
        help=(
            "validation-only scan of every existing ROOT with "
            "delphi_btag_check; atomically refresh checker logs/markers "
            "without invoking the converter"
        ),
    )
    parser.add_argument(
        "--checker",
        type=Path,
        help="delphi_btag_check executable (default: REPO/build/delphi_btag_check)",
    )
    parser.add_argument(
        "--check-workers",
        type=int,
        default=1,
        help="parallel direct checker scans during refresh (default: 1)",
    )
    parser.add_argument("--key4hep-release", default="2026-04-08")
    args = parser.parse_args(argv)

    if args.hash_workers < 1:
        parser.error("--hash-workers must be positive")
    if args.check_workers < 1:
        parser.error("--check-workers must be positive")

    campaign = args.campaign_dir.expanduser().resolve()
    source_dir = args.source_dir.expanduser().resolve()
    repo = Path(__file__).resolve().parents[2]
    checker_executable = (
        args.checker.expanduser().resolve()
        if args.checker
        else repo / "build/delphi_btag_check"
    )
    reserved_output = campaign / f"AUDIT_QQPS_V94C_91P25_{args.mode.upper()}.json"
    requested_output = lexical_absolute(args.output or reserved_output)
    protected_environment_files = (
        Path(__file__).resolve(),
        repo / "scripts/data-reco/batch_sdst_mc.sh",
        repo / "delphi_edm4hep/bin/delphi_btag_check.cpp",
        checker_executable,
        repo / "build/delphi_sdst_pass",
    )
    try:
        output = validate_report_destination(
            requested_output,
            protected_files=protected_environment_files,
            root_policies=(
                (campaign, (reserved_output,)),
                (source_dir, ()),
            ),
        )
    except ReportDestinationError as error:
        print(f"ERROR: unsafe audit report destination: {error}", file=sys.stderr)
        return 2
    logs_dir = campaign / "logs"
    expected_ids = set(OFFICIAL_IDS)
    failures: list[dict[str, Any]] = []

    def fail(code: str, *, file_id: int | None = None, **details: Any) -> None:
        item: dict[str, Any] = {"code": code}
        if file_id is not None:
            item["id"] = file_id
        item.update(details)
        failures.append(item)

    if not campaign.is_dir():
        fail("campaign_directory_missing", path=str(campaign))
    if not source_dir.is_dir():
        fail("source_directory_missing", path=str(source_dir))
    if not logs_dir.is_dir():
        fail("logs_directory_missing", path=str(logs_dir))

    refresh_result: dict[str, Any] | None = None
    if args.refresh_checker_evidence:
        try:
            refresh_result = refresh_checker_evidence(
                campaign=campaign,
                source_dir=source_dir,
                logs_dir=logs_dir,
                mode=args.mode,
                checker_executable=checker_executable,
                workers=args.check_workers,
            )
        except (OSError, RuntimeError) as error:
            fail("checker_evidence_refresh_failed", error=str(error))

    source_ids, source_duplicates = matching_ids(source_dir, SOURCE_RE)
    root_ids, root_duplicates = matching_ids(campaign, ROOT_RE)
    marker_ids, marker_duplicates = matching_ids(campaign, MARKER_RE)
    converter_log_ids, converter_log_duplicates = matching_ids(
        logs_dir, CONVERTER_LOG_RE
    )

    checker_ids: set[int] = set()
    checker_log_duplicates: list[str] = []
    checker_other_mode: list[str] = []
    if logs_dir.is_dir():
        for path in sorted(logs_dir.iterdir(), key=lambda item: item.name):
            match = CHECKER_LOG_RE.fullmatch(path.name)
            if not match:
                continue
            file_id = int(match.group(1))
            mode = match.group(2)
            if mode != args.mode:
                checker_other_mode.append(path.name)
                continue
            if file_id in checker_ids:
                checker_log_duplicates.append(path.name)
            checker_ids.add(file_id)

    inventories = {
        "source_sdst": (source_ids, source_duplicates),
        "output_root": (root_ids, root_duplicates),
        "completion_marker": (marker_ids, marker_duplicates),
        "converter_log": (converter_log_ids, converter_log_duplicates),
        "checker_log": (checker_ids, checker_log_duplicates),
    }
    inventory_json: dict[str, Any] = {}
    for name, (actual, duplicates) in inventories.items():
        missing = sorted(expected_ids - actual)
        extra = sorted(actual - expected_ids)
        inventory_json[name] = {
            "count": len(actual),
            "missing_ids": missing,
            "extra_ids": extra,
            "duplicate_names": duplicates,
        }
        if missing:
            fail(f"{name}_missing", ids=missing)
        if extra:
            fail(f"{name}_extra", ids=extra)
        if duplicates:
            fail(f"{name}_duplicate", names=duplicates)

    if checker_other_mode:
        fail("checker_logs_for_other_mode", names=checker_other_mode)
    inventory_json["checker_logs_for_other_mode"] = checker_other_mode

    all_edm_roots = (
        sorted(path.name for path in campaign.glob("*.edm4hep.root"))
        if campaign.is_dir()
        else []
    )
    expected_root_names = {
        f"qqps_91.25_{file_id}.edm4hep.root" for file_id in OFFICIAL_IDS
    }
    unexpected_edm_roots = sorted(set(all_edm_roots) - expected_root_names)
    if unexpected_edm_roots:
        fail("unexpected_edm4hep_roots", names=unexpected_edm_roots)
    inventory_json["unexpected_edm4hep_roots"] = unexpected_edm_roots

    all_markers = (
        sorted(path.name for path in campaign.glob("*.edm4hep.root.complete"))
        if campaign.is_dir()
        else []
    )
    expected_marker_names = {f"{name}.complete" for name in expected_root_names}
    unexpected_markers = sorted(set(all_markers) - expected_marker_names)
    if unexpected_markers:
        fail("unexpected_completion_markers", names=unexpected_markers)
    inventory_json["unexpected_completion_markers"] = unexpected_markers

    expected_converter_log_names = {
        f"qqps_91.25_{file_id}.log" for file_id in OFFICIAL_IDS
    }
    expected_checker_log_names = {
        f"qqps_91.25_{file_id}.{args.mode}.validation.log"
        for file_id in OFFICIAL_IDS
    }
    all_qqps_logs = (
        sorted(path.name for path in logs_dir.glob("qqps_91.25_*.log"))
        if logs_dir.is_dir()
        else []
    )
    unexpected_qqps_logs = sorted(
        set(all_qqps_logs)
        - expected_converter_log_names
        - expected_checker_log_names
    )
    if unexpected_qqps_logs:
        fail("unexpected_qqps_logs", names=unexpected_qqps_logs)
    inventory_json["unexpected_qqps_logs"] = unexpected_qqps_logs

    scratch_dir = campaign / ".scratch"
    scratch_entries = (
        sorted_relative(scratch_dir.rglob("*"), campaign)
        if scratch_dir.is_dir()
        else []
    )
    temporary_paths: list[Path] = []
    if campaign.is_dir():
        for path in campaign.rglob("*"):
            relative = path.relative_to(campaign)
            if relative.parts and relative.parts[0] == ".scratch":
                continue
            name = path.name
            if (
                ".tmp." in name
                or name.endswith(".tmp")
                or name.endswith(".tmp.root")
                or re.fullmatch(r"fort\.\d+", name)
                or name in {"PDLINPUT", "input.sdst"}
            ):
                temporary_paths.append(path)
    temporary_names = sorted_relative(temporary_paths, campaign)
    if scratch_entries:
        fail("scratch_not_empty", paths=scratch_entries)
    if temporary_names:
        fail("temporary_or_scratch_artifacts", paths=temporary_names)
    inventory_json["scratch"] = {
        "directory_present": scratch_dir.is_dir(),
        "entries": scratch_entries,
    }
    inventory_json["temporary_or_scratch_artifacts"] = temporary_names

    source_rows: list[str] = []
    source_bytes = 0
    for file_id in OFFICIAL_IDS:
        path = source_dir / f"qqps_91.25_{file_id}.sdst"
        if not path.is_file() or path.is_symlink():
            if path.exists() or path.is_symlink():
                fail("source_not_regular", file_id=file_id, path=str(path))
            continue
        size = path.stat().st_size
        source_bytes += size
        source_rows.append(f"{file_id}\t{path.name}\t{size}")
    inventory_json["source_sdst"]["total_bytes"] = source_bytes
    inventory_json["source_sdst"]["manifest_sha256"] = digest_rows(source_rows)
    inventory_json["ignored_xsdst_files"] = (
        sorted(path.name for path in source_dir.glob("*.xsdst"))
        if source_dir.is_dir()
        else []
    )

    existing_roots = [
        campaign / f"qqps_91.25_{file_id}.edm4hep.root"
        for file_id in OFFICIAL_IDS
        if (campaign / f"qqps_91.25_{file_id}.edm4hep.root").is_file()
        and not (campaign / f"qqps_91.25_{file_id}.edm4hep.root").is_symlink()
    ]
    root_hashes: dict[Path, str] = {}
    with ThreadPoolExecutor(max_workers=args.hash_workers) as executor:
        future_paths = {executor.submit(sha256_file, path): path for path in existing_roots}
        for future, path in sorted(
            ((future, path) for future, path in future_paths.items()),
            key=lambda item: item[1].name,
        ):
            try:
                root_hashes[path] = future.result()
            except OSError as error:
                fail("root_hash_failed", path=str(path), error=str(error))

    expected_recalculated = 1 if args.mode == "recalc" else 0
    active_checker_sha256 = (
        sha256_file(checker_executable) if checker_executable.is_file() else None
    )
    file_results: list[dict[str, Any]] = []
    total_checker_entries = 0
    total_frames_checked = 0
    total_log_entries = 0
    total_marker_entries = 0
    total_bytes = 0
    diagnostic_totals = {key: 0 for key in DIAGNOSTIC_COUNTERS}
    failure_counter_totals = {key: 0 for key in REQUIRED_ZERO_COUNTERS}

    required_marker_keys = {
        "input",
        "run",
        "btag_mode",
        "source",
        "recalculated",
        "primary_vertex_policy",
        "iflpvt",
        "size_bytes",
        "validated_utc",
        "validation_method",
        "checker_sha256",
        "validation",
    }

    for file_id in OFFICIAL_IDS:
        stem = f"qqps_91.25_{file_id}"
        source = source_dir / f"{stem}.sdst"
        root = campaign / f"{stem}.edm4hep.root"
        marker = campaign / f"{stem}.edm4hep.root.complete"
        converter_log = logs_dir / f"{stem}.log"
        checker_log = logs_dir / f"{stem}.{args.mode}.validation.log"
        result: dict[str, Any] = {
            "id": file_id,
            "expected_run": -file_id,
            "source": source.name,
            "root": root.name,
            "marker": marker.name,
            "converter_log": f"logs/{converter_log.name}",
            "checker_log": f"logs/{checker_log.name}",
        }

        if not root.is_file() or root.is_symlink():
            if root.exists() or root.is_symlink():
                fail("root_not_regular", file_id=file_id, path=str(root))
            file_results.append(result)
            continue

        root_size = root.stat().st_size
        total_bytes += root_size
        result["size_bytes"] = root_size
        if root_size == 0:
            fail("root_empty", file_id=file_id, path=str(root))
        if root in root_hashes:
            result["root_sha256"] = root_hashes[root]

        converter_text: str | None = None
        if converter_log.is_file() and not converter_log.is_symlink():
            converter_text = converter_log.read_text(
                encoding="utf-8", errors="replace"
            )
            result["converter_log_sha256"] = sha256_file(converter_log)
            written = [int(value) for value in WRITTEN_RE.findall(converter_text)]
            if len(written) != 1:
                fail(
                    "converter_written_count_cardinality",
                    file_id=file_id,
                    found=written,
                )
            else:
                result["converter_log_entries"] = written[0]
                total_log_entries += written[0]

            expected_input_line = f"input={source}"
            input_lines = [
                line for line in converter_text.splitlines() if line.startswith("input=")
            ]
            if input_lines != [expected_input_line]:
                fail(
                    "converter_input_provenance",
                    file_id=file_id,
                    expected=expected_input_line,
                    actual=input_lines,
                )

            successful_calibrations = CALIBRATION_RE.findall(converter_text)
            result["successful_calibration_files"] = successful_calibrations
            if successful_calibrations != [CALIBRATION_FILE]:
                fail(
                    "calibration_file",
                    file_id=file_id,
                    expected=[CALIBRATION_FILE],
                    actual=successful_calibrations,
                )
        elif converter_log.exists() or converter_log.is_symlink():
            fail("converter_log_not_regular", file_id=file_id, path=str(converter_log))

        checker_raw: str | None = None
        checker: dict[str, Any] | None = None
        if checker_log.is_file() and not checker_log.is_symlink():
            result["checker_log_sha256"] = sha256_file(checker_log)
            try:
                checker_raw, checker = parse_checker_log(checker_log)
            except (OSError, ValueError) as error:
                fail("checker_log_parse", file_id=file_id, error=str(error))
            if checker is not None:
                result["checker"] = checker
                total_checker_entries += checker["entries"]
                total_frames_checked += checker["frames_checked"]
                for key in DIAGNOSTIC_COUNTERS:
                    diagnostic_totals[key] += checker[key]
                for key in REQUIRED_ZERO_COUNTERS:
                    failure_counter_totals[key] += checker[key]

                expected_checker = {
                    "status": "PASS",
                    "expected_run": -file_id,
                    "source": "sDST",
                    "identity_source": "sDST_EVT",
                    "btag_mode": args.mode,
                    "recalculated_expected": expected_recalculated,
                    "chi2_pv_contract": "attached-only-v1",
                    "chi2_pv_roundoff_tolerance": "0.25",
                    "provenance_schema": "source-local-v1",
                    "beamspot_status_source": "sDST_BTAGCFG_BeamSpotErrorCode",
                    "primary_vertex_policy": "keep-delana",
                    "primary_vertex_policy_expected": "keep-delana",
                    "iflpvt": 0,
                    "legacy_fdst_beamspot_fallback_requested": 0,
                    "legacy_fdst_beamspot_fallback_used": 0,
                    "reference_provenance_schema": "not-applicable",
                    "legacy_reference_beamspot_fallback_requested": 0,
                    "legacy_reference_beamspot_fallback_used": 0,
                    "identity_reference": "none",
                    "reference_entries": 0,
                    "reference_source_local_provenance_frames": 0,
                    "legacy_reference_fallback_frames": 0,
                }
                for key, expected in expected_checker.items():
                    if checker[key] != expected:
                        fail(
                            "checker_provenance",
                            file_id=file_id,
                            field=key,
                            expected=expected,
                            actual=checker[key],
                        )
                if checker["entries"] != checker["frames_checked"]:
                    fail(
                        "checker_entry_frame_mismatch",
                        file_id=file_id,
                        entries=checker["entries"],
                        frames_checked=checker["frames_checked"],
                    )
                if checker["source_local_provenance_frames"] != checker["entries"]:
                    fail(
                        "checker_source_local_provenance_count",
                        file_id=file_id,
                        expected=checker["entries"],
                        actual=checker["source_local_provenance_frames"],
                    )
                if checker["legacy_sdst_provenance_frames"] != 0 or checker[
                    "legacy_fdst_fallback_frames"
                ] != 0:
                    fail("checker_legacy_provenance", file_id=file_id)
                if checker["identity_reference"] == "none":
                    if checker["reference_entries"] != 0:
                        fail(
                            "checker_reference_without_path",
                            file_id=file_id,
                            reference_entries=checker["reference_entries"],
                        )
                elif checker["reference_entries"] != checker["entries"]:
                    fail(
                        "checker_reference_entry_mismatch",
                        file_id=file_id,
                        entries=checker["entries"],
                        reference_entries=checker["reference_entries"],
                        identity_reference=checker["identity_reference"],
                    )
                for key in REQUIRED_ZERO_COUNTERS:
                    if checker[key] != 0:
                        fail(
                            "checker_failure_counter",
                            file_id=file_id,
                            counter=key,
                            actual=checker[key],
                        )
                if args.mode == "recalc":
                    expected_invalid = (
                        checker["aabtag_not_invoked_events"]
                        + checker["bad_status_events"]
                    )
                    validity_equalities = {
                        "aabtag_not_invoked_events": checker["beamspot_error_events"],
                        "aabtag_invalid_events": expected_invalid,
                        "event_probability_nans": 9 * expected_invalid,
                        "thrust_nans": 4 * expected_invalid,
                    }
                    for key, expected in validity_equalities.items():
                        if checker[key] != expected:
                            fail(
                                "checker_validity_contract",
                                file_id=file_id,
                                field=key,
                                expected=expected,
                                actual=checker[key],
                            )
        elif checker_log.exists() or checker_log.is_symlink():
            fail("checker_log_not_regular", file_id=file_id, path=str(checker_log))

        marker_values: dict[str, str] | None = None
        if marker.is_file() and not marker.is_symlink():
            result["marker_sha256"] = sha256_file(marker)
            try:
                marker_values = parse_marker(marker)
            except (OSError, ValueError) as error:
                fail("marker_parse", file_id=file_id, error=str(error))
            if marker_values is not None:
                missing_marker_keys = sorted(required_marker_keys - marker_values.keys())
                if missing_marker_keys:
                    fail(
                        "marker_schema",
                        file_id=file_id,
                        missing=missing_marker_keys,
                    )
                expected_marker = {
                    "input": str(source),
                    "run": str(-file_id),
                    "btag_mode": args.mode,
                    "source": "sDST",
                    "recalculated": str(expected_recalculated),
                    "primary_vertex_policy": "keep-delana",
                    "iflpvt": "0",
                    "size_bytes": str(root_size),
                }
                for key, expected in expected_marker.items():
                    if marker_values.get(key) != expected:
                        fail(
                            "marker_provenance",
                            file_id=file_id,
                            field=key,
                            expected=expected,
                            actual=marker_values.get(key),
                        )
                if marker_values.get("validation_method") != "direct_delphi_btag_check":
                    fail(
                        "marker_validation_method",
                        file_id=file_id,
                        actual=marker_values.get("validation_method"),
                    )
                result["marker_recorded_checker_sha256"] = marker_values.get(
                    "checker_sha256"
                )
                if marker_values.get("checker_sha256") != active_checker_sha256:
                    fail(
                        "marker_checker_digest",
                        file_id=file_id,
                        expected=active_checker_sha256,
                        actual=marker_values.get("checker_sha256"),
                    )
                if checker_raw is not None and marker_values.get("validation") != checker_raw:
                    fail("marker_checker_summary_mismatch", file_id=file_id)
                if "validation" in marker_values:
                    try:
                        marker_checker = parse_key_values(marker_values["validation"])
                        marker_entries = int(marker_checker["entries"])
                        result["marker_entries"] = marker_entries
                        total_marker_entries += marker_entries
                    except (KeyError, ValueError) as error:
                        fail(
                            "marker_validation_parse",
                            file_id=file_id,
                            error=str(error),
                        )
        elif marker.exists() or marker.is_symlink():
            fail("marker_not_regular", file_id=file_id, path=str(marker))

        counts = {
            key: result[key]
            for key in ("converter_log_entries", "marker_entries")
            if key in result
        }
        if checker is not None:
            counts["root_entries_from_checker"] = checker["entries"]
            counts["checker_frames_checked"] = checker["frames_checked"]
        if len(counts) == 4 and len(set(counts.values())) != 1:
            fail("per_file_event_count_mismatch", file_id=file_id, counts=counts)
        result["event_counts"] = counts
        file_results.append(result)

    payload_totals = {
        "root_entries_from_checker": total_checker_entries,
        "checker_frames_checked": total_frames_checked,
        "converter_log_entries": total_log_entries,
        "completion_marker_entries": total_marker_entries,
    }
    for source, observed in payload_totals.items():
        if observed != PAYLOAD_EVENT_COUNT:
            fail(
                "campaign_event_total",
                source=source,
                expected=PAYLOAD_EVENT_COUNT,
                actual=observed,
            )

    if args.mode == "recalc":
        expected_invalid = (
            diagnostic_totals["aabtag_not_invoked_events"]
            + diagnostic_totals["bad_status_events"]
        )
        aggregate_validity_equalities = {
            "aabtag_not_invoked_events": diagnostic_totals["beamspot_error_events"],
            "aabtag_invalid_events": expected_invalid,
            "event_probability_nans": 9 * expected_invalid,
            "thrust_nans": 4 * expected_invalid,
        }
        for key, expected in aggregate_validity_equalities.items():
            if diagnostic_totals[key] != expected:
                fail(
                    "aggregate_validity_contract",
                    field=key,
                    expected=expected,
                    actual=diagnostic_totals[key],
                )

    if len(file_results) != OFFICIAL_FILE_COUNT:
        fail(
            "internal_file_result_count",
            expected=OFFICIAL_FILE_COUNT,
            actual=len(file_results),
        )

    root_rows = [
        "\t".join(
            (
                str(item["id"]),
                item["root"],
                str(item.get("size_bytes", "MISSING")),
                str(item.get("root_sha256", "MISSING")),
                str(item.get("event_counts", {}).get("root_entries_from_checker", "MISSING")),
            )
        )
        for item in file_results
    ]
    evidence_rows = [
        "\t".join(
            (
                str(item["id"]),
                str(item.get("converter_log_sha256", "MISSING")),
                str(item.get("checker_log_sha256", "MISSING")),
                str(item.get("marker_sha256", "MISSING")),
            )
        )
        for item in file_results
    ]

    # These paths describe the environment in which this audit is running.
    # In particular, the current build products are not evidence of which
    # binaries originally produced an already-existing campaign.
    audit_environment_files = {
        "audit_script": Path(__file__).resolve(),
        "batch_driver": repo / "scripts/data-reco/batch_sdst_mc.sh",
        "checker_source": repo / "delphi_edm4hep/bin/delphi_btag_check.cpp",
        "checker_executable": checker_executable,
        "converter_executable": repo / "build/delphi_sdst_pass",
    }
    audit_environment_digests: dict[str, str | None] = {}
    for name, path in audit_environment_files.items():
        try:
            audit_environment_digests[name] = (
                sha256_file(path) if path.is_file() else None
            )
        except OSError:
            audit_environment_digests[name] = None

    marker_recorded_checker_digests = sorted(
        {
            value
            for item in file_results
            if (value := item.get("marker_recorded_checker_sha256")) is not None
        }
    )

    failures.sort(
        key=lambda item: (
            item["code"],
            item.get("id", -1),
            json.dumps(item, sort_keys=True),
        )
    )
    payload: dict[str, Any] = {
        "schema_version": 2,
        "status": "PASS" if not failures else "FAIL",
        "dataset": {
            "name": "DELPHI v94c qqps 91.25 GeV Short DST simulation",
            "scope": "complete official CERN-origin record 81437 SDST payload",
            "btag_mode": args.mode,
            "official_ids": list(OFFICIAL_IDS),
            "official_file_count": OFFICIAL_FILE_COUNT,
        },
        "catalogue_and_payload_event_counts": {
            "catalogue_metadata_events": CATALOGUE_EVENT_COUNT,
            "payload_authoritative_events": PAYLOAD_EVENT_COUNT,
            "catalogue_minus_payload": CATALOGUE_EVENT_COUNT
            - PAYLOAD_EVENT_COUNT,
            "acceptance_basis": (
                "exact sum independently agreed by ROOT/podio checker entries, "
                "checker frames, converter logs, and completion markers"
            ),
        },
        "cern_open_data": CATALOGUE_RECORD,
        "paths": {
            "campaign": str(campaign),
            "source": str(source_dir),
            "output": str(output),
        },
        "provenance": {
            "audit_environment": {
                "repository_commit": git_head(repo),
                "key4hep_release_requested_for_checker_refresh": (
                    args.key4hep_release
                ),
                "files_sha256": audit_environment_digests,
                "scope": (
                    "Hashes of files visible when the audit ran; current build "
                    "products are not producer-binary provenance."
                ),
            },
            "recorded_validation_evidence": {
                "marker_checker_sha256_values": marker_recorded_checker_digests,
                "active_audit_checker_sha256": active_checker_sha256,
                "all_markers_bind_active_audit_checker": (
                    marker_recorded_checker_digests == [active_checker_sha256]
                    if active_checker_sha256 is not None
                    else False
                ),
                "markers_may_have_been_refreshed_by_this_audit": bool(
                    refresh_result
                ),
            },
            "recorded_production_evidence": {
                "expected_recalc_calibration_file": (
                    CALIBRATION_FILE if args.mode == "recalc" else None
                ),
                "calibration_file_checked_from_converter_logs": (
                    args.mode == "recalc"
                ),
                "producer_repository_commit_recorded": None,
                "producer_converter_sha256_recorded": None,
                "scope": (
                    "The historical markers did not record the producer "
                    "repository commit or converter-binary digest."
                ),
            },
        },
        "checker_evidence_refresh": refresh_result,
        "inventory": inventory_json,
        "payload": {
            "event_totals": payload_totals,
            "total_output_bytes": total_bytes,
            "required_failure_counter_totals": failure_counter_totals,
            "diagnostic_counter_totals": diagnostic_totals,
        },
        "digests": {
            "source_size_manifest_sha256": digest_rows(source_rows),
            "output_content_manifest_sha256": digest_rows(root_rows),
            "validation_evidence_manifest_sha256": digest_rows(evidence_rows),
            "manifest_encoding": "one UTF-8 tab-separated row per ID, LF terminated",
        },
        "files": file_results,
        "failure_count": len(failures),
        "failures": failures,
    }

    try:
        atomic_write_json(output, payload)
    except (OSError, ReportDestinationError) as error:
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stdout)
        print(
            f"ERROR: could not write audit report atomically: {error}",
            file=sys.stderr,
        )
        return 2
    print(
        f"{payload['status']} mode={args.mode} files={len(root_ids)}/166 "
        f"events={total_checker_entries}/{PAYLOAD_EVENT_COUNT} "
        f"bytes={total_bytes} failures={len(failures)} output={output}"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
