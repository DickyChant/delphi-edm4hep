#!/usr/bin/env python3
"""Audit a complete 429-tape ``batch_94c.sh`` Phase-A AABTAG campaign.

The audit is read-only with respect to campaign products.  It verifies the
immutable ``delphi-batch94c-v3`` configuration, derives the exact tape set
independently from ``worklist.txt`` and ``al.all``, requires exact Phase-A
ROOT/marker/log inventories, and aggregates the all-frame
source-specific ``delphi_btag_check`` summaries recorded in validation logs
and completion markers. It verifies the marker's content SHA-256 against every
ROOT file but does not deserialize ROOT payloads or invoke a converter/checker.

One JSON report is written atomically.  A campaign that is still locked,
incomplete, changing during the scan, or structurally inconsistent receives a
FAIL report and a nonzero exit status.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from report_destination import (
    ReportDestinationError,
    atomic_write_report_text,
    validate_report_destination,
)


EXPECTED_TAPES = 429
EXPECTED_WORKLIST_ROWS = 1_892
EXPECTED_ENTRIES = 5_756_545
EXPECTED_WORKLIST_SHA256 = (
    "5e6c2c0992a0ebfa34236779d7b2f0ac424fab459446bce4cb3758539162920e"
)
EXPECTED_AL_ALL_SHA256 = (
    "ab7776cd4d92b5248a74bf2d3a20628854299fc3b2bec67fbac4c0c210934d80"
)
CAMPAIGN_FORMAT = "delphi-batch94c-v3"
MARKER_FORMAT = "delphi-batch94c-complete-v2"
EXPECTED_MODE = "recalc"

CAMPAIGN_KEYS = (
    "format",
    "btag_mode",
    "primary_vertex_policy",
    "worklist",
    "worklist_sha256",
    "key4hep_release",
    "edmbin",
    "sdst_binary_sha256",
    "fdst_binary_sha256",
    "btag_checker_sha256",
    "image",
    "raw_base",
    "tape_base",
)

MARKER_KEYS = (
    "format",
    "phase",
    "item",
    "output",
    "events",
    "output_size_bytes",
    "output_sha256",
    "btag_mode",
    "primary_vertex_policy",
    "btag_checker_sha256",
    "sdst_btag_check_summary",
    "fdst_btag_check_summary",
    "campaign_sha256",
)

# This is the complete, ordered schema printed by the current checker.  Exact
# matching deliberately rejects evidence made by an older/partial validator.
CHECKER_KEYS = (
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
)

CHECKER_TEXT_KEYS = {
    "status",
    "expected_run",
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
CHECKER_INTEGER_KEYS = set(CHECKER_KEYS) - CHECKER_TEXT_KEYS

STRUCTURAL_FAILURE_KEYS = (
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

DIAGNOSTIC_KEYS = (
    "bad_status_events",
    "beamspot_error_events",
    "aabtag_not_invoked_events",
    "aabtag_invalid_events",
    "event_probability_nans",
    "thrust_nans",
    "tracks",
    "track_chi2_pv_roundoff_values",
    "track_chi2_pv_undefined_values",
    "unresolved_particle_indices",
    "truncated_events",
)

WORKLIST_RE = re.compile(
    r"^(ED[0-9]+\.[0-9]+)\s+([1-9][0-9]*)\s+"
    r"(Y[0-9]+\.[0-9]+(?:,Y[0-9]+\.[0-9]+)*)$"
)
TAPE_RE = re.compile(r"^Y[0-9]+\.[0-9]+$")
HARNESS_RE = re.compile(
    r"^delphi_edm4hep::harness:\s+wrote\s+([0-9]+)\s+events\s+to(?:\s|$)",
    re.MULTILINE,
)
FATAL_LOG_RE = re.compile(
    r"Segmentation violation|segmentation fault|core dumped|"
    r"\bKilled\b|No space left on device|Cannot allocate memory|std::bad_alloc|"
    r"terminate called|bus error|Traceback \(most recent call last\)|"
    r"harness::run:|converter exited successfully but produced no nonempty output",
    re.IGNORECASE,
)

Fingerprint = Tuple[int, int, int, int, int]


def fingerprint_from_stat(info: os.stat_result) -> Fingerprint:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
    )


def regular_fingerprint(path: Path) -> Fingerprint:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"not a regular non-symlink file: {path}")
    return fingerprint_from_stat(info)


def read_regular_stable(path: Path) -> Tuple[bytes, Fingerprint]:
    before = regular_fingerprint(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"opened object is not a regular file: {path}")
        chunks: List[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = regular_fingerprint(path)
    opened_before = fingerprint_from_stat(opened)
    opened_final = fingerprint_from_stat(opened_after)
    if before != opened_before or before != opened_final or before != after:
        raise ValueError(f"file changed while it was read: {path}")
    payload = b"".join(chunks)
    if len(payload) != before[3]:
        raise ValueError(f"short read: {path}")
    return payload, before


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_regular_stable(path: Path) -> Tuple[str, Fingerprint]:
    before = regular_fingerprint(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags)
    digest = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"opened object is not a regular file: {path}")
        while True:
            chunk = os.read(descriptor, 4 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = regular_fingerprint(path)
    if (
        before != fingerprint_from_stat(opened)
        or before != fingerprint_from_stat(opened_after)
        or before != after
    ):
        raise ValueError(f"file changed while it was hashed: {path}")
    return digest.hexdigest(), before


def decode_text(payload: bytes, path: Path) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"not UTF-8 text: {path}: {error}") from error


def parse_key_value_text(
    text: str, path: Path, expected_keys: Sequence[str]
) -> Dict[str, str]:
    values: Dict[str, str] = {}
    order: List[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw or "=" not in raw:
            raise ValueError(f"{path}:{number}: malformed key=value line")
        key, value = raw.split("=", 1)
        if not key or key in values:
            raise ValueError(f"{path}:{number}: empty or duplicate key {key!r}")
        values[key] = value
        order.append(key)
    if tuple(order) != tuple(expected_keys):
        missing = sorted(set(expected_keys) - set(order))
        extra = sorted(set(order) - set(expected_keys))
        raise ValueError(
            f"{path}: key schema/order mismatch: missing={missing}, extra={extra}, "
            f"actual_order={order}"
        )
    return values


def parse_checker_summary(raw: str, context: str) -> Dict[str, Any]:
    values: Dict[str, str] = {}
    order: List[str] = []
    try:
        tokens = shlex.split(raw, posix=True)
    except ValueError as error:
        raise ValueError(f"{context}: checker summary quoting error: {error}") from error
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"{context}: malformed checker token {token!r}")
        key, value = token.split("=", 1)
        if not key or key in values:
            raise ValueError(f"{context}: empty or duplicate checker key {key!r}")
        values[key] = value
        order.append(key)
    if tuple(order) != CHECKER_KEYS:
        missing = sorted(set(CHECKER_KEYS) - set(order))
        extra = sorted(set(order) - set(CHECKER_KEYS))
        raise ValueError(
            f"{context}: checker schema/order mismatch: missing={missing}, "
            f"extra={extra}, actual_order={order}"
        )
    converted: Dict[str, Any] = dict(values)
    for key in CHECKER_INTEGER_KEYS:
        try:
            converted[key] = int(values[key])
        except ValueError as error:
            raise ValueError(
                f"{context}: checker field {key!r} is not an integer"
            ) from error
        if converted[key] < 0:
            raise ValueError(f"{context}: checker field {key!r} is negative")
    return converted


def derive_worklist_tapes(text: str, path: Path) -> Tuple[List[str], int]:
    rows = text.splitlines()
    if not rows:
        raise ValueError(f"empty worklist: {path}")
    tapes = set()
    raw_segments = set()
    for number, line in enumerate(rows, start=1):
        match = WORKLIST_RE.fullmatch(line)
        if not match:
            raise ValueError(f"{path}:{number}: malformed worklist row")
        raw_segment = match.group(1)
        if raw_segment in raw_segments:
            raise ValueError(f"{path}:{number}: duplicate raw segment {raw_segment}")
        raw_segments.add(raw_segment)
        row_tapes = match.group(3).split(",")
        if len(row_tapes) != len(set(row_tapes)):
            raise ValueError(f"{path}:{number}: duplicate tape within row")
        tapes.update(row_tapes)
    return sorted(tapes), len(rows)


def parse_tape_manifest(text: str, path: Path) -> List[str]:
    rows = text.splitlines()
    if not rows:
        raise ValueError(f"empty tape manifest: {path}")
    for number, tape in enumerate(rows, start=1):
        if not TAPE_RE.fullmatch(tape):
            raise ValueError(f"{path}:{number}: malformed tape name {tape!r}")
    if rows != sorted(set(rows)):
        raise ValueError(f"{path}: tape rows are not bytewise sorted and unique")
    return rows


def digest_rows(rows: Iterable[str]) -> str:
    return hashlib.sha256(
        "".join(f"{row}\n" for row in rows).encode("utf-8")
    ).hexdigest()


def git_head(repo: Path) -> Optional[str]:
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


def acquire_campaign_read_lock(
    lock_path: Path,
) -> Tuple[Optional[int], bool, Optional[str]]:
    try:
        regular_fingerprint(lock_path)
        descriptor = os.open(str(lock_path), os.O_RDONLY)
    except (OSError, ValueError) as error:
        return None, False, str(error)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        return None, True, None
    except OSError as error:
        os.close(descriptor)
        return None, False, str(error)
    # Keep the shared lock for the entire audit.  This gives all inventory and
    # marker reads one idle-campaign snapshot and prevents a new batch writer
    # from acquiring its exclusive, nonblocking lock midway through the scan.
    return descriptor, False, None


def release_campaign_read_lock(descriptor: Optional[int]) -> None:
    if descriptor is None:
        return
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def fatal_matches(text: str, relative_log: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if FATAL_LOG_RE.search(line):
            matches.append(
                {
                    "log": relative_log,
                    "line": number,
                    "text": line[:500],
                }
            )
    return matches


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    atomic_write_report_text(path, rendered)


def absolute_without_resolving_final(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "campaign",
        type=Path,
        help="complete batch_94c.sh v2 campaign root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "atomic JSON destination (default: "
            "CAMPAIGN/AUDIT_SDST_AABTAG_CURRENT.json)"
        ),
    )
    parser.add_argument(
        "--checker",
        type=Path,
        help=(
            "checker binary to content-bind (default: the campaign.conf "
            "edmbin/delphi_btag_check)"
        ),
    )
    args = parser.parse_args(argv)

    campaign = Path(os.path.realpath(os.path.expanduser(str(args.campaign))))
    requested_output = absolute_without_resolving_final(
        args.output
        if args.output is not None
        else campaign / "AUDIT_SDST_AABTAG_CURRENT.json"
    )
    repo = Path(__file__).resolve().parents[2]
    reserved_output = campaign / "AUDIT_SDST_AABTAG_CURRENT.json"
    early_protected = [Path(__file__).resolve()]
    if args.checker is not None:
        early_protected.append(absolute_without_resolving_final(args.checker))
    try:
        output = validate_report_destination(
            requested_output,
            protected_files=early_protected,
            root_policies=((campaign, (reserved_output,)),),
        )
    except ReportDestinationError as error:
        print(f"ERROR: unsafe audit report destination: {error}", file=sys.stderr)
        return 2
    failures: List[Dict[str, Any]] = []

    def fail(code: str, **details: Any) -> None:
        item: Dict[str, Any] = {"code": code}
        item.update(details)
        failures.append(item)

    if not campaign.is_dir():
        fail("campaign_directory_missing", path=str(campaign))

    lock_path = campaign / ".campaign.lock"
    campaign_lock_fd, active, lock_error = acquire_campaign_read_lock(lock_path)
    if lock_error is not None:
        fail("campaign_lock_invalid", path=str(lock_path), error=lock_error)
    if active:
        fail("campaign_active", path=str(lock_path))

    config_path = campaign / "campaign.conf"
    worklist_path = campaign / "worklist.txt"
    worklist_run_path = campaign / "worklist.run"
    al_all_path = campaign / "al.all"
    al_run_path = campaign / "al.run"

    config: Dict[str, str] = {}
    config_sha256: Optional[str] = None
    config_fingerprint: Optional[Fingerprint] = None
    config_payload: Optional[bytes] = None
    try:
        config_payload, config_fingerprint = read_regular_stable(config_path)
        config_sha256 = sha256_bytes(config_payload)
        config = parse_key_value_text(
            decode_text(config_payload, config_path), config_path, CAMPAIGN_KEYS
        )
    except (OSError, ValueError) as error:
        fail("campaign_config_invalid", path=str(config_path), error=str(error))

    expected_config_values = {
        "format": CAMPAIGN_FORMAT,
        "btag_mode": EXPECTED_MODE,
        "primary_vertex_policy": "keep-delana",
        "worklist_sha256": EXPECTED_WORKLIST_SHA256,
    }
    for key, expected in expected_config_values.items():
        if config.get(key) != expected:
            fail(
                "campaign_config_value_mismatch",
                key=key,
                expected=expected,
                actual=config.get(key),
            )
    if config.get("worklist"):
        configured_worklist = Path(
            os.path.realpath(os.path.expanduser(config["worklist"]))
        )
        if configured_worklist != worklist_path:
            fail(
                "campaign_worklist_path_mismatch",
                expected=str(worklist_path),
                actual=str(configured_worklist),
            )

    support_payloads: Dict[str, bytes] = {}
    support_fingerprints: Dict[str, Fingerprint] = {}
    for name, path in (
        ("worklist", worklist_path),
        ("worklist_run", worklist_run_path),
        ("al_all", al_all_path),
        ("al_run", al_run_path),
    ):
        try:
            payload, item_fingerprint = read_regular_stable(path)
            support_payloads[name] = payload
            support_fingerprints[name] = item_fingerprint
        except (OSError, ValueError) as error:
            fail("campaign_support_file_invalid", name=name, path=str(path), error=str(error))

    worklist_sha256 = (
        sha256_bytes(support_payloads["worklist"])
        if "worklist" in support_payloads
        else None
    )
    al_all_sha256 = (
        sha256_bytes(support_payloads["al_all"])
        if "al_all" in support_payloads
        else None
    )
    if worklist_sha256 != EXPECTED_WORKLIST_SHA256:
        fail(
            "worklist_sha256_mismatch",
            expected=EXPECTED_WORKLIST_SHA256,
            actual=worklist_sha256,
        )
    if al_all_sha256 != EXPECTED_AL_ALL_SHA256:
        fail(
            "al_all_sha256_mismatch",
            expected=EXPECTED_AL_ALL_SHA256,
            actual=al_all_sha256,
        )
    if config.get("worklist_sha256") != worklist_sha256:
        fail(
            "config_worklist_sha256_mismatch",
            configured=config.get("worklist_sha256"),
            actual=worklist_sha256,
        )
    if support_payloads.get("worklist_run") != support_payloads.get("worklist"):
        fail("worklist_run_is_not_full_worklist")
    if support_payloads.get("al_run") != support_payloads.get("al_all"):
        fail("al_run_is_not_full_tape_inventory")

    worklist_tapes: List[str] = []
    worklist_rows = 0
    al_all_tapes: List[str] = []
    if "worklist" in support_payloads:
        try:
            worklist_tapes, worklist_rows = derive_worklist_tapes(
                decode_text(support_payloads["worklist"], worklist_path),
                worklist_path,
            )
        except ValueError as error:
            fail("worklist_parse_failed", error=str(error))
    if "al_all" in support_payloads:
        try:
            al_all_tapes = parse_tape_manifest(
                decode_text(support_payloads["al_all"], al_all_path), al_all_path
            )
        except ValueError as error:
            fail("al_all_parse_failed", error=str(error))
    if worklist_rows != EXPECTED_WORKLIST_ROWS:
        fail(
            "worklist_row_count_mismatch",
            expected=EXPECTED_WORKLIST_ROWS,
            actual=worklist_rows,
        )
    if len(worklist_tapes) != EXPECTED_TAPES:
        fail(
            "worklist_tape_count_mismatch",
            expected=EXPECTED_TAPES,
            actual=len(worklist_tapes),
        )
    if len(al_all_tapes) != EXPECTED_TAPES:
        fail(
            "al_all_tape_count_mismatch",
            expected=EXPECTED_TAPES,
            actual=len(al_all_tapes),
        )
    if worklist_tapes != al_all_tapes:
        fail(
            "worklist_al_all_tape_mismatch",
            only_in_worklist=sorted(set(worklist_tapes) - set(al_all_tapes)),
            only_in_al_all=sorted(set(al_all_tapes) - set(worklist_tapes)),
        )
    tapes = al_all_tapes if al_all_tapes else worklist_tapes

    checker_path = (
        absolute_without_resolving_final(args.checker)
        if args.checker is not None
        else Path(config.get("edmbin", str(repo / "build"))) / "delphi_btag_check"
    )
    if not config.get("tape_base") and output != reserved_output:
        print(
            "ERROR: unsafe audit report destination: cannot validate an external "
            "report until campaign.conf supplies tape_base",
            file=sys.stderr,
        )
        release_campaign_read_lock(campaign_lock_fd)
        return 2
    tape_base = Path(config.get("tape_base", "/nonexistent"))
    protected_sources = tuple(
        tape_base / tape.split(".", 1)[0] / f"{tape}.al" for tape in tapes
    )
    try:
        output = validate_report_destination(
            output,
            protected_files=(
                Path(__file__).resolve(),
                checker_path,
                *protected_sources,
            ),
            root_policies=((tape_base, ()),),
        )
    except ReportDestinationError as error:
        print(f"ERROR: unsafe audit report destination: {error}", file=sys.stderr)
        release_campaign_read_lock(campaign_lock_fd)
        return 2
    checker_sha256: Optional[str] = None
    checker_fingerprint: Optional[Fingerprint] = None
    try:
        checker_sha256, checker_fingerprint = sha256_regular_stable(checker_path)
        if not os.access(str(checker_path), os.X_OK):
            fail("checker_not_executable", path=str(checker_path))
    except (OSError, ValueError) as error:
        fail("checker_invalid", path=str(checker_path), error=str(error))
    if config.get("btag_checker_sha256") != checker_sha256:
        fail(
            "checker_sha256_mismatch",
            configured=config.get("btag_checker_sha256"),
            actual=checker_sha256,
        )

    intermediate_dir = campaign / "intermediates"
    log_dir = campaign / "logs"
    scratch_dir = campaign / "scratch"
    expected_roots = {f"inter_{tape}.root" for tape in tapes}
    expected_markers = {f"inter_{tape}.root.complete" for tape in tapes}
    expected_converter_logs = {f"A_{tape}.log" for tape in tapes}
    expected_validation_logs = {
        f"A_{tape}.sdst.validation.log" for tape in tapes
    }
    expected_logs = expected_converter_logs | expected_validation_logs

    def immediate_names(directory: Path, code: str) -> set:
        try:
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("not a directory or is a symlink")
            return {entry.name for entry in directory.iterdir()}
        except (OSError, ValueError) as error:
            fail(code, path=str(directory), error=str(error))
            return set()

    intermediate_names = immediate_names(
        intermediate_dir, "intermediate_directory_invalid"
    )
    log_names = immediate_names(log_dir, "log_directory_invalid")
    allowed_intermediate_names = expected_roots | expected_markers
    inventory = {
        "roots": {
            "expected": len(expected_roots),
            "present_names": len(expected_roots & intermediate_names),
            "missing": sorted(expected_roots - intermediate_names),
        },
        "markers": {
            "expected": len(expected_markers),
            "present_names": len(expected_markers & intermediate_names),
            "missing": sorted(expected_markers - intermediate_names),
        },
        "logs": {
            "expected": len(expected_logs),
            "present_names": len(expected_logs & log_names),
            "missing": sorted(expected_logs - log_names),
        },
        "unexpected_intermediate_entries": sorted(
            intermediate_names - allowed_intermediate_names
        ),
        "unexpected_log_entries": sorted(log_names - expected_logs),
    }
    for kind in ("roots", "markers", "logs"):
        if inventory[kind]["missing"]:
            fail(f"missing_{kind}", names=inventory[kind]["missing"])
    if inventory["unexpected_intermediate_entries"]:
        fail(
            "unexpected_intermediate_entries",
            names=inventory["unexpected_intermediate_entries"],
        )
    if inventory["unexpected_log_entries"]:
        fail("unexpected_log_entries", names=inventory["unexpected_log_entries"])

    aggregate = {key: 0 for key in CHECKER_INTEGER_KEYS}
    file_results: List[Dict[str, Any]] = []
    manifest_rows: List[str] = []
    output_bytes = 0
    marker_output_bytes = 0
    source_input_bytes = 0
    summaries_parsed = 0
    fatal_log_findings: List[Dict[str, Any]] = []
    for tape in tapes:
        output_path = intermediate_dir / f"inter_{tape}.root"
        marker_path = Path(f"{output_path}.complete")
        log_path = log_dir / f"A_{tape}.log"
        validation_path = log_dir / f"A_{tape}.sdst.validation.log"
        yvid = tape.split(".", 1)[0]
        source_path = tape_base / yvid / f"{tape}.al"
        per_file_errors: List[str] = []
        result: Dict[str, Any] = {
            "tape": tape,
            "output": f"intermediates/{output_path.name}",
            "marker": f"intermediates/{marker_path.name}",
            "log": f"logs/{log_path.name}",
            "validation_log": f"logs/{validation_path.name}",
            "source": str(source_path),
        }

        try:
            output_before = regular_fingerprint(output_path)
            if output_before[3] <= 0:
                per_file_errors.append("output ROOT is empty")
            result["output_size_bytes"] = output_before[3]
            output_bytes += output_before[3]
        except (OSError, ValueError) as error:
            output_before = None
            per_file_errors.append(str(error))

        try:
            source_info = regular_fingerprint(source_path)
            result["source_size_bytes"] = source_info[3]
            source_input_bytes += source_info[3]
        except (OSError, ValueError) as error:
            source_info = None
            per_file_errors.append(f"source: {error}")

        marker: Dict[str, str] = {}
        marker_text = ""
        marker_sha = "missing"
        try:
            marker_payload, _ = read_regular_stable(marker_path)
            marker_text = decode_text(marker_payload, marker_path)
            marker_sha = sha256_bytes(marker_payload)
            marker = parse_key_value_text(marker_text, marker_path, MARKER_KEYS)
            result["marker_sha256"] = marker_sha
        except (OSError, ValueError) as error:
            per_file_errors.append(f"marker: {error}")

        log_text = ""
        log_sha = "missing"
        validation_sha = "missing"
        summary_raw = ""
        checker: Optional[Dict[str, Any]] = None
        try:
            log_payload, _ = read_regular_stable(log_path)
            log_text = decode_text(log_payload, log_path)
            log_sha = sha256_bytes(log_payload)
            result["log_sha256"] = log_sha
            fatal_log_findings.extend(
                fatal_matches(log_text, f"logs/{log_path.name}")
            )
            harness_counts = [int(value) for value in HARNESS_RE.findall(log_text)]
            if len(harness_counts) != 1:
                per_file_errors.append(
                    f"converter harness count is not unique: {harness_counts}"
                )
        except (OSError, ValueError) as error:
            per_file_errors.append(f"converter log: {error}")

        try:
            validation_payload, _ = read_regular_stable(validation_path)
            validation_text = decode_text(validation_payload, validation_path)
            validation_sha = sha256_bytes(validation_payload)
            result["validation_log_sha256"] = validation_sha
            summary_lines = [
                line
                for line in validation_text.splitlines()
                if line.startswith("status=")
            ]
            if len(summary_lines) != 1:
                raise ValueError(
                    f"expected exactly one checker summary, found {len(summary_lines)}"
                )
            summary_raw = summary_lines[0]
            checker = parse_checker_summary(summary_raw, str(validation_path))
            summaries_parsed += 1
            for key in CHECKER_INTEGER_KEYS:
                aggregate[key] += checker[key]
            harness_counts = [int(value) for value in HARNESS_RE.findall(log_text)]
            if harness_counts != [checker["entries"]]:
                per_file_errors.append(
                    "harness/checker entry mismatch: "
                    f"{harness_counts} != [{checker['entries']}]"
                )
            nonempty_lines = [line for line in validation_text.splitlines() if line]
            if not nonempty_lines or nonempty_lines[-1] != summary_raw:
                per_file_errors.append(
                    "checker summary is not the final nonempty validation-log line"
                )
        except (OSError, ValueError) as error:
            per_file_errors.append(f"validation log/checker: {error}")

        if checker is not None:
            semantic_expected: Dict[str, Any] = {
                "status": "PASS",
                "expected_run": "data",
                "source": "sDST",
                "identity_source": "sDST_EVT",
                "btag_mode": EXPECTED_MODE,
                "recalculated_expected": 1,
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
            for key, expected in semantic_expected.items():
                if checker[key] != expected:
                    per_file_errors.append(
                        f"checker {key}: expected {expected!r}, got {checker[key]!r}"
                    )
            if checker["entries"] <= 0:
                per_file_errors.append("checker entries is not positive")
            if checker["frames_checked"] != checker["entries"]:
                per_file_errors.append("checker frames_checked differs from entries")
            if checker["source_local_provenance_frames"] != checker["entries"]:
                per_file_errors.append(
                    "source-local provenance frame count differs from entries"
                )
            if checker["legacy_sdst_provenance_frames"] != 0 or checker[
                "legacy_fdst_fallback_frames"
            ] != 0:
                per_file_errors.append("current campaign used legacy provenance")
            leaf_failures = sum(checker[key] for key in STRUCTURAL_FAILURE_KEYS)
            if checker["failures"] != leaf_failures:
                per_file_errors.append(
                    "checker failures differs from structural-counter sum: "
                    f"{checker['failures']} != {leaf_failures}"
                )
            if checker["failures"] != 0:
                per_file_errors.append("checker failures is nonzero")
            for key in STRUCTURAL_FAILURE_KEYS:
                if checker[key] != 0:
                    per_file_errors.append(f"checker {key} is nonzero")
            if checker["aabtag_not_invoked_events"] != checker["beamspot_error_events"]:
                per_file_errors.append(
                    "AABTAG not-invoked count differs from beamspot-error count"
                )
            expected_invalid = (
                checker["aabtag_not_invoked_events"]
                + checker["bad_status_events"]
            )
            if checker["aabtag_invalid_events"] != expected_invalid:
                per_file_errors.append(
                    "AABTAG invalid count differs from disjoint not-invoked + "
                    f"bad-status sum: {checker['aabtag_invalid_events']} != "
                    f"{expected_invalid}"
                )
            if checker["event_probability_nans"] != 9 * expected_invalid:
                per_file_errors.append(
                    "probability NaN count differs from 9 per invalid event"
                )
            if checker["thrust_nans"] != 4 * expected_invalid:
                per_file_errors.append(
                    "thrust NaN count differs from 4 per invalid event"
                )
            result["entries"] = checker["entries"]
            result["diagnostics"] = {
                key: checker[key] for key in DIAGNOSTIC_KEYS
            }

        if marker:
            try:
                marker_checker = parse_checker_summary(
                    marker["sdst_btag_check_summary"], str(marker_path)
                )
                if checker is not None and marker_checker != checker:
                    per_file_errors.append(
                        "marker/log parsed checker summaries differ"
                    )
            except (KeyError, OSError, ValueError) as error:
                per_file_errors.append(f"marker checker summary: {error}")
            expected_marker_text = {
                "format": MARKER_FORMAT,
                "phase": "A",
                "item": tape,
                "output": output_path.name,
                "btag_mode": EXPECTED_MODE,
                "primary_vertex_policy": "keep-delana",
                "btag_checker_sha256": checker_sha256,
                "sdst_btag_check_summary": summary_raw,
                "fdst_btag_check_summary": "not-applicable",
                "campaign_sha256": config_sha256,
            }
            for key, expected in expected_marker_text.items():
                if marker.get(key) != expected:
                    per_file_errors.append(
                        f"marker {key}: expected {expected!r}, got {marker.get(key)!r}"
                    )
            try:
                marker_events = int(marker["events"])
                marker_size = int(marker["output_size_bytes"])
                if marker_events < 0 or marker_size < 0:
                    raise ValueError("negative marker count")
                marker_output_bytes += marker_size
                if checker is not None and marker_events != checker["entries"]:
                    per_file_errors.append("marker events differs from checker entries")
                if output_before is not None and marker_size != output_before[3]:
                    per_file_errors.append("marker output size differs from ROOT stat")
                if output_before is not None:
                    output_sha, output_after_hash = sha256_regular_stable(output_path)
                    if output_after_hash != output_before:
                        per_file_errors.append("output ROOT changed while hashing")
                    if marker.get("output_sha256") != output_sha:
                        per_file_errors.append("marker output SHA-256 differs from ROOT")
            except (KeyError, ValueError) as error:
                per_file_errors.append(f"marker numeric field: {error}")

        if output_before is not None:
            try:
                if regular_fingerprint(output_path) != output_before:
                    per_file_errors.append("output ROOT changed during audit")
            except (OSError, ValueError) as error:
                per_file_errors.append(f"output final stat: {error}")
        if source_info is not None:
            try:
                if regular_fingerprint(source_path) != source_info:
                    per_file_errors.append("source input changed during audit")
            except (OSError, ValueError) as error:
                per_file_errors.append(f"source final stat: {error}")

        if checker is not None and output_before is not None:
            manifest_rows.append(
                "\t".join(
                    (
                        tape,
                        output_path.name,
                        str(output_before[3]),
                        str(checker["entries"]),
                        marker_sha,
                        log_sha,
                        validation_sha,
                    )
                )
            )
        if per_file_errors:
            result["errors"] = per_file_errors
            fail("tape_validation_failed", tape=tape, errors=per_file_errors)
        file_results.append(result)

    if summaries_parsed != EXPECTED_TAPES:
        fail(
            "checker_summary_count_mismatch",
            expected=EXPECTED_TAPES,
            actual=summaries_parsed,
        )
    if aggregate["entries"] != EXPECTED_ENTRIES:
        fail(
            "aggregate_entry_count_mismatch",
            expected=EXPECTED_ENTRIES,
            actual=aggregate["entries"],
        )
    if aggregate["frames_checked"] != EXPECTED_ENTRIES:
        fail(
            "aggregate_frames_checked_mismatch",
            expected=EXPECTED_ENTRIES,
            actual=aggregate["frames_checked"],
        )
    if aggregate["failures"] != 0:
        fail("aggregate_checker_failures_nonzero", actual=aggregate["failures"])
    for key in STRUCTURAL_FAILURE_KEYS:
        if aggregate[key] != 0:
            fail("aggregate_structural_counter_nonzero", counter=key, actual=aggregate[key])
    if aggregate["aabtag_not_invoked_events"] != aggregate["beamspot_error_events"]:
        fail(
            "aggregate_invocation_beamspot_mismatch",
            not_invoked=aggregate["aabtag_not_invoked_events"],
            beamspot_errors=aggregate["beamspot_error_events"],
        )
    expected_invalid = (
        aggregate["aabtag_not_invoked_events"] + aggregate["bad_status_events"]
    )
    if aggregate["aabtag_invalid_events"] != expected_invalid:
        fail(
            "aggregate_invalid_union_mismatch",
            invalid=aggregate["aabtag_invalid_events"],
            expected=expected_invalid,
        )
    if aggregate["event_probability_nans"] != 9 * expected_invalid:
        fail(
            "aggregate_probability_nan_contract_mismatch",
            actual=aggregate["event_probability_nans"],
            expected=9 * expected_invalid,
        )
    if aggregate["thrust_nans"] != 4 * expected_invalid:
        fail(
            "aggregate_thrust_nan_contract_mismatch",
            actual=aggregate["thrust_nans"],
            expected=4 * expected_invalid,
        )
    if output_bytes != marker_output_bytes:
        fail(
            "aggregate_marker_output_size_mismatch",
            root_bytes=output_bytes,
            marker_bytes=marker_output_bytes,
        )

    scratch_entries: List[str] = []
    if scratch_dir.exists() or scratch_dir.is_symlink():
        try:
            scratch_info = scratch_dir.lstat()
            if not stat.S_ISDIR(scratch_info.st_mode):
                fail("scratch_directory_invalid", path=str(scratch_dir))
            else:
                scratch_entries = sorted(
                    str(path.relative_to(campaign)) for path in scratch_dir.rglob("*")
                )
        except OSError as error:
            fail("scratch_scan_failed", error=str(error))
    if scratch_entries:
        fail("scratch_not_empty", paths=scratch_entries)

    temporary_paths: List[str] = []
    if campaign.is_dir():
        try:
            for path in campaign.rglob("*"):
                relative = path.relative_to(campaign)
                if relative.parts and relative.parts[0] == "scratch":
                    continue
                if path == output:
                    continue
                name = path.name
                if (
                    ".tmp." in name
                    or name.endswith(".tmp")
                    or name.endswith(".tmp.root")
                    or name.startswith(".phdst_input_")
                    or re.fullmatch(r"fort\.[0-9]+", name)
                    or name in {"PDLINPUT", "core"}
                    or name.startswith("core.")
                ):
                    temporary_paths.append(str(relative))
        except OSError as error:
            fail("temporary_scan_failed", error=str(error))
    temporary_paths.sort()
    if temporary_paths:
        fail("temporary_artifacts_remain", paths=temporary_paths)
    if fatal_log_findings:
        fail("fatal_log_signatures", matches=fatal_log_findings)

    try:
        if (
            config_fingerprint is not None
            and regular_fingerprint(config_path) != config_fingerprint
        ):
            fail("campaign_config_changed_during_audit")
        for name, path in (
            ("worklist", worklist_path),
            ("worklist_run", worklist_run_path),
            ("al_all", al_all_path),
            ("al_run", al_run_path),
        ):
            if (
                name in support_fingerprints
                and regular_fingerprint(path) != support_fingerprints[name]
            ):
                fail("campaign_support_file_changed_during_audit", name=name)
    except (OSError, ValueError) as error:
        fail("campaign_snapshot_recheck_failed", error=str(error))
    if checker_sha256 is not None and checker_fingerprint is not None:
        try:
            final_checker_sha, final_checker_fingerprint = sha256_regular_stable(
                checker_path
            )
            if (
                final_checker_sha != checker_sha256
                or final_checker_fingerprint != checker_fingerprint
            ):
                fail("checker_changed_during_audit")
        except (OSError, ValueError) as error:
            fail("checker_final_hash_failed", error=str(error))

    try:
        disk = os.statvfs(str(campaign))
        disk_json: Dict[str, Any] = {
            "filesystem_total_bytes": disk.f_blocks * disk.f_frsize,
            "filesystem_free_bytes": disk.f_bavail * disk.f_frsize,
        }
    except OSError as error:
        disk_json = {"error": str(error)}

    try:
        audit_script_sha256, _ = sha256_regular_stable(Path(__file__).resolve())
    except (OSError, ValueError):
        audit_script_sha256 = None

    result: Dict[str, Any] = {
        "audit": {
            "format": "delphi-batch94c-sdst-recalc-audit-v2",
            "status": "PASS" if not failures else "FAIL",
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "campaign": str(campaign),
            "output": str(output),
            "scope": (
                "read-only exact-inventory and recorded all-frame checker-evidence "
                "audit; no ROOT payload was opened and no converter/checker was run"
            ),
            "campaign_active": active,
            "audit_environment_repository_head": git_head(repo),
            "audit_script_sha256": audit_script_sha256,
        },
        "campaign": {
            "config": config,
            "campaign_conf_sha256": config_sha256,
            "worklist_rows": worklist_rows,
            "worklist_tapes": len(worklist_tapes),
            "al_all_tapes": len(al_all_tapes),
            "worklist_al_all_exact_match": worklist_tapes == al_all_tapes,
            "worklist_sha256": worklist_sha256,
            "expected_worklist_sha256": EXPECTED_WORKLIST_SHA256,
            "al_all_sha256": al_all_sha256,
            "expected_al_all_sha256": EXPECTED_AL_ALL_SHA256,
            "full_worklist_selected": (
                support_payloads.get("worklist_run")
                == support_payloads.get("worklist")
            ),
            "full_tape_inventory_selected": (
                support_payloads.get("al_run") == support_payloads.get("al_all")
            ),
        },
        "checker_provenance": {
            "audit_environment_executable_path": str(checker_path),
            "audit_environment_executable_sha256": checker_sha256,
            "producer_recorded_checker_sha256": config.get(
                "btag_checker_sha256"
            ),
            "audit_environment_matches_producer_record": (
                checker_sha256 == config.get("btag_checker_sha256")
            ),
            "exact_current_summary_schema": list(CHECKER_KEYS),
        },
        "inventory": inventory,
        "payload": {
            "expected_files": EXPECTED_TAPES,
            "files_with_parsed_checker_summary": summaries_parsed,
            "expected_entries": EXPECTED_ENTRIES,
            "entries": aggregate["entries"],
            "frames_checked": aggregate["frames_checked"],
            "output_bytes": output_bytes,
            "marker_recorded_output_bytes": marker_output_bytes,
            "source_input_bytes": source_input_bytes,
            "file_manifest_sha256": digest_rows(manifest_rows),
        },
        "aggregate_checker_counters": aggregate,
        "structural_failure_counter_totals": {
            "failures": aggregate["failures"],
            **{key: aggregate[key] for key in STRUCTURAL_FAILURE_KEYS},
        },
        "diagnostics": {
            **{key: aggregate[key] for key in DIAGNOSTIC_KEYS},
            "probability_nans_per_invalid_event": (
                aggregate["event_probability_nans"]
                / aggregate["aabtag_invalid_events"]
                if aggregate["aabtag_invalid_events"]
                else None
            ),
            "thrust_nans_per_invalid_event": (
                aggregate["thrust_nans"] / aggregate["aabtag_invalid_events"]
                if aggregate["aabtag_invalid_events"]
                else None
            ),
            "note": (
                "raw bad-status, beamspot skips, combined invalid events, NaNs, "
                "track counts, unresolved particle indices, and truncation are "
                "diagnostics; the invocation/validity and NaN multiplicity "
                "equalities above are mandatory"
            ),
        },
        "cleanup": {
            "temporary_artifacts": temporary_paths,
            "scratch_entries": scratch_entries,
            "fatal_log_matches": fatal_log_findings,
        },
        "disk": disk_json,
        "files": file_results,
        "failures": failures,
    }

    try:
        atomic_write_json(output, result)
    except (OSError, ValueError) as error:
        print(json.dumps(result, indent=2, sort_keys=True), file=sys.stdout)
        print(f"ERROR: could not write audit report atomically: {error}", file=sys.stderr)
        release_campaign_read_lock(campaign_lock_fd)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    release_campaign_read_lock(campaign_lock_fd)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
