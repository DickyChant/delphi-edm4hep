#!/usr/bin/env python3
"""Archived audit of the exact historical 429-tape stored-BTG data campaign.

This is a metadata/read-only audit of products already validated frame by
frame by ``delphi_btag_check``.  It does not open the EDM4hep payloads or run
the converter again.  Instead it verifies the exact official manifest, every
product/marker/log set, marker-to-log provenance, recorded filesystem sizes,
and the aggregate all-frame validation counters and identity comparisons.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any


EXPECTED_TAPES = 429
EXPECTED_ENTRIES = 5_756_545
EXPECTED_MODE = "bank"
EXPECTED_MANIFEST_SHA256 = (
    "ab7776cd4d92b5248a74bf2d3a20628854299fc3b2bec67fbac4c0c210934d80"
)
EXPECTED_WORKLIST_SHA256 = (
    "5e6c2c0992a0ebfa34236779d7b2f0ac424fab459446bce4cb3758539162920e"
)

COUNTER_KEYS = (
    "entries",
    "frames_checked",
    "failures",
    "frame_read_failures",
    "run_failures",
    "reference_entries",
    "reference_entry_count_failures",
    "reference_frame_read_failures",
    "identity_failures",
    "mode_failures",
    "recalculated_failures",
    "provenance_failures",
    "source_local_provenance_frames",
    "legacy_sdst_provenance_frames",
    "legacy_fdst_fallback_frames",
    "missing_event_parameters",
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
    "pv_size_failures",
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
)

ZERO_FAILURE_KEYS = (
    "failures",
    "frame_read_failures",
    "run_failures",
    "reference_entry_count_failures",
    "reference_frame_read_failures",
    "identity_failures",
    "mode_failures",
    "recalculated_failures",
    "provenance_failures",
    "missing_event_parameters",
    "event_vector_length_failures",
    "event_probability_range_failures",
    "thrust_range_failures",
    "missing_track_parameters",
    "missing_collections",
    "track_vector_length_failures",
    "track_probability_nonfinite_failures",
    "track_probability_range_failures",
    "pv_size_failures",
    "particle_index_range_failures",
    "bad_status_events",
    "aabtag_not_invoked_events",
    "aabtag_invalid_events",
    "validity_contract_failures",
    "truncation_failures",
    "attached_consistency_failures",
)

FATAL_LOG_RE = re.compile(
    r"Segmentation violation|segmentation fault|core dumped|Killed|"
    r"No space left|event-by-event bank/identity validation failed|"
    r"converter exited successfully but produced no nonempty output",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_key_value_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw:
            continue
        if "=" not in raw:
            raise ValueError(f"{path}:{line_number}: missing '='")
        key, value = raw.split("=", 1)
        if not key or key in result:
            raise ValueError(f"{path}:{line_number}: invalid/duplicate key {key!r}")
        result[key] = value
    return result


def parse_summary(path: Path) -> tuple[str, dict[str, str]]:
    lines = [line for line in path.read_text().splitlines() if line]
    if len(lines) != 1:
        raise ValueError(f"{path}: expected exactly one nonempty summary line")
    line = lines[0]
    result: dict[str, str] = {}
    for token in shlex.split(line, posix=True):
        if "=" not in token:
            raise ValueError(f"{path}: malformed summary token {token!r}")
        key, value = token.split("=", 1)
        if key in result:
            raise ValueError(f"{path}: duplicate summary key {key!r}")
        result[key] = value
    return line, result


def int_field(values: dict[str, str], key: str, context: Path) -> int:
    if key not in values:
        raise ValueError(f"{context}: missing summary key {key!r}")
    try:
        return int(values[key])
    except ValueError as error:
        raise ValueError(
            f"{context}: summary key {key!r} is not an integer: {values[key]!r}"
        ) from error


def derive_worklist_tapes(worklist: Path) -> list[str]:
    tapes: set[str] = set()
    line_re = re.compile(r"^ED[0-9]+\.[0-9]+\s+[0-9]+\s+(Y[0-9]+\.[0-9]+(?:,Y[0-9]+\.[0-9]+)*)$")
    for line_number, line in enumerate(worklist.read_text().splitlines(), 1):
        match = line_re.fullmatch(line)
        if not match:
            raise ValueError(f"{worklist}:{line_number}: malformed worklist line")
        tapes.update(match.group(1).split(","))
    return sorted(tapes)


def git_head(repo: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_default = Path(__file__).resolve().parents[2]
    parser.add_argument(
        "campaign",
        nargs="?",
        type=Path,
        default=repo_default / "reruns/btag_recalc/legacy_closure/data_full_94c",
    )
    parser.add_argument("--output", type=Path, help="write JSON here (also print it)")
    parser.add_argument(
        "--checker",
        type=Path,
        default=repo_default / "build/delphi_btag_check",
        help="checker binary whose digest every completion marker must record",
    )
    args = parser.parse_args()

    campaign = args.campaign.resolve()
    repo = Path(__file__).resolve().parents[2]
    checker = args.checker.resolve()
    issues: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            issues.append(message)

    try:
        config = parse_key_value_file(campaign / "campaign.conf")
        manifest_path = campaign / "tapes.manifest"
        manifest = [line for line in manifest_path.read_text().splitlines() if line]
        unique_manifest = sorted(set(manifest))
        worklist = Path(config["worklist"])
        worklist_tapes = derive_worklist_tapes(worklist)
        reference_dir = Path(config["reference_dir"])
        source_base = Path(config["source_base"])
    except (OSError, KeyError, ValueError) as error:
        result = {
            "audit": {
                "status": "FAIL",
                "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "campaign": str(campaign),
                "scope": "metadata audit failed during campaign discovery",
            },
            "issues": [str(error)],
        }
        rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(rendered)
        print(rendered, end="")
        return 1

    manifest_sha = sha256(manifest_path)
    worklist_sha = sha256(worklist)
    check(len(manifest) == EXPECTED_TAPES, "manifest entry count is not 429")
    check(len(unique_manifest) == EXPECTED_TAPES, "manifest is not 429 unique tapes")
    check(manifest == unique_manifest, "manifest is not unique and bytewise sorted")
    check(manifest == worklist_tapes, "manifest differs from tapes derived from worklist")
    check(manifest_sha == EXPECTED_MANIFEST_SHA256, "unexpected manifest SHA-256")
    check(worklist_sha == EXPECTED_WORKLIST_SHA256, "unexpected worklist SHA-256")
    check(config.get("format") == "delphi-data-btag-campaign-v1", "bad campaign format")
    check(config.get("btag_mode") == EXPECTED_MODE, "campaign mode is not bank")
    check(config.get("expected_recalculated") == "0", "campaign recalc flag is not zero")
    check(config.get("tape_count") == str(EXPECTED_TAPES), "campaign tape count is not 429")
    check(config.get("manifest_sha256") == manifest_sha, "campaign manifest hash mismatch")
    check(config.get("worklist_sha256") == worklist_sha, "campaign worklist hash mismatch")
    check(config.get("reference_btag_mode") == "recalc", "reference mode is not recalc")
    active_checker_sha = sha256(checker) if checker.is_file() else "missing"
    check(active_checker_sha != "missing", f"checker binary not found: {checker}")

    expected_roots = {f"inter_{tape}.root" for tape in manifest}
    expected_markers = {f"inter_{tape}.root.complete" for tape in manifest}
    expected_validation_logs = {f"{tape}.bank.validation.log" for tape in manifest}
    expected_converter_logs = {f"{tape}.bank.log" for tape in manifest}

    actual_roots = {path.name for path in campaign.glob("inter_*.root") if path.is_file()}
    actual_markers = {
        path.name for path in campaign.glob("inter_*.root.complete") if path.is_file()
    }
    log_dir = campaign / "logs"
    actual_validation_logs = {
        path.name for path in log_dir.glob("*.bank.validation.log") if path.is_file()
    }
    actual_converter_logs = {
        path.name for path in log_dir.glob("*.bank.log") if path.is_file()
    }

    set_failures = {
        "missing_roots": sorted(expected_roots - actual_roots),
        "extra_roots": sorted(actual_roots - expected_roots),
        "missing_markers": sorted(expected_markers - actual_markers),
        "extra_markers": sorted(actual_markers - expected_markers),
        "missing_validation_logs": sorted(expected_validation_logs - actual_validation_logs),
        "extra_validation_logs": sorted(actual_validation_logs - expected_validation_logs),
        "missing_converter_logs": sorted(expected_converter_logs - actual_converter_logs),
        "extra_converter_logs": sorted(actual_converter_logs - expected_converter_logs),
    }
    for name, values in set_failures.items():
        check(not values, f"nonempty exact-set failure: {name}")

    totals = {key: 0 for key in COUNTER_KEYS}
    validation_failures: list[dict[str, Any]] = []
    marker_failures: list[dict[str, Any]] = []
    fatal_converter_logs: list[str] = []
    output_bytes = 0
    marker_output_bytes = 0
    input_bytes = 0
    reference_bytes = 0
    event_counts: list[int] = []
    validated_times: list[dt.datetime] = []
    successful_identity_pairs = 0

    for tape in manifest:
        output = campaign / f"inter_{tape}.root"
        marker_path = Path(f"{output}.complete")
        validation_path = log_dir / f"{tape}.bank.validation.log"
        converter_path = log_dir / f"{tape}.bank.log"
        yvid = tape.split(".", 1)[0]
        expected_input = source_base / yvid / f"{tape}.al"
        expected_reference = reference_dir / f"inter_{tape}.root"

        if not all(path.is_file() for path in (output, marker_path, validation_path, converter_path)):
            continue

        per_validation: list[str] = []
        try:
            summary_line, summary = parse_summary(validation_path)
            for key in COUNTER_KEYS:
                totals[key] += int_field(summary, key, validation_path)
            entries = int_field(summary, "entries", validation_path)
            event_counts.append(entries)
            if summary.get("status") != "PASS":
                per_validation.append("status is not PASS")
            if summary.get("expected_run") != "data":
                per_validation.append("expected_run is not data")
            if summary.get("source") != "sDST":
                per_validation.append("source is not sDST")
            if summary.get("identity_source") != "sDST_EVT":
                per_validation.append("identity source is not sDST_EVT")
            if summary.get("btag_mode") != "bank":
                per_validation.append("btag_mode is not bank")
            if summary.get("recalculated_expected") != "0":
                per_validation.append("recalculated_expected is not zero")
            if summary.get("identity_reference") != str(expected_reference):
                per_validation.append("identity reference path mismatch")
            if summary.get("legacy_reference_beamspot_fallback_requested") != "1":
                per_validation.append("legacy reference fallback was not explicit")
            if int_field(summary, "frames_checked", validation_path) != entries:
                per_validation.append("frames_checked differs from entries")
            if int_field(summary, "reference_entries", validation_path) != entries:
                per_validation.append("reference_entries differs from entries")
            reference_schema = summary.get("reference_provenance_schema")
            if reference_schema == "source-local-v1":
                if summary.get("legacy_reference_beamspot_fallback_used") != "0":
                    per_validation.append(
                        "reference fallback reported used for source-local reference"
                    )
            elif reference_schema == "legacy-missing-source-local-btagcfg":
                if summary.get("legacy_reference_beamspot_fallback_used") != "1":
                    per_validation.append("legacy reference fallback was not used")
                if int_field(
                    summary, "legacy_reference_fallback_frames", validation_path
                ) != entries:
                    per_validation.append(
                        "legacy reference fallback count differs from entries"
                    )
            else:
                per_validation.append(
                    f"unsupported reference provenance schema {reference_schema!r}"
                )
            schema = summary.get("provenance_schema")
            if schema == "source-local-v1":
                if int_field(
                    summary, "source_local_provenance_frames", validation_path
                ) != entries:
                    per_validation.append(
                        "source-local provenance count differs from entries"
                    )
            elif schema == "legacy-sdst-evt":
                if int_field(
                    summary, "legacy_sdst_provenance_frames", validation_path
                ) != entries:
                    per_validation.append(
                        "legacy sDST provenance count differs from entries"
                    )
            else:
                per_validation.append(f"unsupported provenance schema {schema!r}")
            for key in ZERO_FAILURE_KEYS:
                if int_field(summary, key, validation_path) != 0:
                    per_validation.append(f"{key} is nonzero")
            if not per_validation:
                successful_identity_pairs += 1
        except (OSError, ValueError) as error:
            summary_line = ""
            per_validation.append(str(error))
        if per_validation:
            validation_failures.append({"tape": tape, "failures": per_validation})

        per_marker: list[str] = []
        try:
            marker = parse_key_value_file(marker_path)
            output_stat = output.stat()
            input_stat = expected_input.stat()
            reference_stat = expected_reference.stat()
            output_bytes += output_stat.st_size
            input_bytes += input_stat.st_size
            reference_bytes += reference_stat.st_size
            marker_output_bytes += int(marker.get("output_size_bytes", "-1"))
            expected_marker_fields = {
                "format": "delphi-data-btag-complete-v1",
                "tape": tape,
                "input": str(expected_input),
                "identity_reference": str(expected_reference),
                "btag_mode": "bank",
                "recalculated": "0",
                "manifest_sha256": manifest_sha,
                "validation_method": "direct_delphi_btag_check",
                "checker_sha256": active_checker_sha,
                "validation": summary_line,
            }
            for key, expected in expected_marker_fields.items():
                if marker.get(key) != expected:
                    per_marker.append(f"{key} mismatch")
            size_fields = {
                "input_size_bytes": input_stat.st_size,
                "identity_reference_size_bytes": reference_stat.st_size,
                "output_size_bytes": output_stat.st_size,
            }
            for key, expected in size_fields.items():
                try:
                    actual = int(marker.get(key, "-1"))
                except ValueError:
                    actual = -1
                if actual != expected:
                    per_marker.append(f"{key} mismatch")
            try:
                validated_times.append(
                    dt.datetime.fromisoformat(marker["validated_utc"].replace("Z", "+00:00"))
                )
            except (KeyError, ValueError):
                per_marker.append("validated_utc missing or malformed")
        except (OSError, ValueError) as error:
            per_marker.append(str(error))
        if per_marker:
            marker_failures.append({"tape": tape, "failures": per_marker})

        try:
            converter_text = converter_path.read_text(errors="replace")
            if FATAL_LOG_RE.search(converter_text):
                fatal_converter_logs.append(tape)
            if summary_line and not converter_text.rstrip().endswith(
                "--- delphi_btag_check ---\n" + summary_line
            ):
                marker_failures.append(
                    {"tape": tape, "failures": ["converter log does not end with checker summary"]}
                )
        except OSError as error:
            fatal_converter_logs.append(f"{tape}: {error}")

    check(not validation_failures, "one or more validation summaries failed")
    check(not marker_failures, "one or more completion markers/log tails failed")
    check(not fatal_converter_logs, "one or more converter logs has a fatal signature")
    check(successful_identity_pairs == EXPECTED_TAPES, "not all 429 identity pairs passed")
    check(totals["entries"] == EXPECTED_ENTRIES, "entry total differs from 5,756,545")
    check(totals["frames_checked"] == EXPECTED_ENTRIES, "frames_checked total mismatch")
    check(totals["reference_entries"] == EXPECTED_ENTRIES, "reference entry total mismatch")
    for key in ZERO_FAILURE_KEYS:
        check(totals[key] == 0, f"aggregate {key} is nonzero")
    check(output_bytes == marker_output_bytes, "marker/output byte totals differ")

    temp_files = sorted(
        str(path.relative_to(campaign)) for path in campaign.glob(".inter_*.tmp.root")
    )
    scratch_entries = sorted(
        str(path.relative_to(campaign)) for path in (campaign / ".scratch").glob("*")
    )
    check(not temp_files, "temporary output files remain")
    check(not scratch_entries, "scratch entries remain")

    reference_markers_missing = [
        tape
        for tape in manifest
        if not Path(f"{reference_dir / f'inter_{tape}.root'}.complete").is_file()
    ]
    check(not reference_markers_missing, "recalculated reference marker(s) missing")

    usage = shutil.disk_usage(campaign)
    script_paths = {
        "campaign_driver": repo
        / "scripts/data-reco/archive_legacy_batch_sdst_data_bank_94c.sh",
        "audit_driver": Path(__file__).resolve(),
        "checker_source": repo / "delphi_edm4hep/bin/delphi_btag_check.cpp",
        "checker_binary": checker,
    }
    software_sha256 = {
        key: sha256(path) if path.is_file() else "missing"
        for key, path in script_paths.items()
    }

    result: dict[str, Any] = {
        "audit": {
            "status": "PASS" if not issues else "FAIL",
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "campaign": str(campaign),
            "scope": (
                "exact official manifest and product/marker/log sets; completion-marker "
                "provenance and recorded sizes; aggregate all-frame validator summaries "
                "including ordered (run,event,fileSeq) reference identity. No conversion "
                "or payload processing was rerun."
            ),
            "repository_sha": git_head(repo),
            "software_sha256": software_sha256,
        },
        "manifest": {
            "expected_tapes": EXPECTED_TAPES,
            "entries": len(manifest),
            "unique_entries": len(unique_manifest),
            "derived_worklist_entries": len(worklist_tapes),
            "exact_worklist_match": manifest == worklist_tapes,
            "manifest_sha256": manifest_sha,
            "expected_manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "worklist_sha256": worklist_sha,
            "expected_worklist_sha256": EXPECTED_WORKLIST_SHA256,
        },
        "sets": {
            "root_files": len(actual_roots),
            "completion_markers": len(actual_markers),
            "validation_logs": len(actual_validation_logs),
            "converter_logs": len(actual_converter_logs),
            **set_failures,
        },
        "payload": {
            "files_checked_from_validator_summaries": len(event_counts),
            "successful_ordered_identity_pairs": successful_identity_pairs,
            "total_entries": totals["entries"],
            "total_reference_entries": totals["reference_entries"],
            "total_frames_checked": totals["frames_checked"],
            "expected_total_entries": EXPECTED_ENTRIES,
            "minimum_entries_per_file": min(event_counts) if event_counts else 0,
            "maximum_entries_per_file": max(event_counts) if event_counts else 0,
            "output_bytes": output_bytes,
            "output_gib": output_bytes / 1024**3,
            "marker_recorded_output_bytes": marker_output_bytes,
            "source_input_bytes": input_bytes,
            "recalculated_reference_bytes": reference_bytes,
        },
        "aggregate_validator_counters": totals,
        "failure_counter_totals": {key: totals[key] for key in ZERO_FAILURE_KEYS},
        "diagnostics": {
            "event_probability_nans": totals["event_probability_nans"],
            "thrust_nans": totals["thrust_nans"],
            "beamspot_error_events": totals["beamspot_error_events"],
            "note": "NaNs are the explicit not-computed sentinel representation and are diagnostic, not structural failures.",
        },
        "provenance": {
            "campaign_config": config,
            "active_checker": str(checker),
            "active_checker_sha256": active_checker_sha,
            "validated_first_utc": min(validated_times).isoformat() if validated_times else None,
            "validated_last_utc": max(validated_times).isoformat() if validated_times else None,
            "reference_markers_missing": reference_markers_missing,
        },
        "cleanup": {
            "temporary_output_files": temp_files,
            "scratch_entries": scratch_entries,
            "fatal_converter_logs": fatal_converter_logs,
        },
        "disk": {
            "filesystem_total_bytes": usage.total,
            "filesystem_used_bytes": usage.used,
            "filesystem_free_bytes": usage.free,
        },
        "failures": {
            "validation": validation_failures,
            "markers_or_log_tails": marker_failures,
        },
        "issues": issues,
    }

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
        temporary.write_text(rendered)
        os.replace(temporary, args.output)
    print(rendered, end="")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
