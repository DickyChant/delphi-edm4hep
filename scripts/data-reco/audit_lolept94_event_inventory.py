#!/usr/bin/env python3
"""Read-only full-event inventory audit for the frozen lolept94_c2 campaign.

The audit independently checks the exact 132-tape manifest, canonical
intermediate/final ROOT and marker inventories, frozen lepton-audit inventory,
per-tape counts in both conversion passes, an empty live scratch area, and the
integrity of every recorded interrupted-product quarantine.  It then reads
every final EDM4hep event and counts exact ``(run,event,fileSeq)`` identities.

The CERN catalog count is retained as metadata.  Acceptance is against the
event occurrences observed in the exact payload inventory, not that catalog
field.  Campaign inputs and frozen authority are never modified; only the
explicit supplemental JSON destination is atomically replaced.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import fcntl
import hashlib
import json
import os
import shlex
import stat
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable

from report_destination import (
    ReportDestinationError,
    atomic_write_report_text,
    lexical_absolute,
    validate_report_destination,
)


REPORT_FORMAT = "delphi-lolept94-c2-event-inventory-audit-v1"
DATASET = "lolept94_c2"
EXPECTED_FILES = 132
EXPECTED_PAYLOAD_EVENTS = 831_002
CATALOG_EVENTS = 828_851
EXPECTED_INPUT_BYTES = 12_076_784_640
EXPECTED_MANIFEST_SHA256 = (
    "68096b0346f93f4952c5a119b7cfe28858882b6947a1da1f6773198add02c54b"
)
IDENTITY_PARAMETERS = (
    "sDST_EVT_runNumber",
    "sDST_EVT_eventNumber",
    "sDST_EVT_fileSeq",
)


class AuditError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular_stat(path: Path, *, allow_empty: bool = False) -> os.stat_result:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise AuditError(f"required regular non-symlink file is missing: {path}")
    if not allow_empty and info.st_size <= 0:
        raise AuditError(f"required file is empty: {path}")
    return info


def load_key_values(path: Path) -> Dict[str, str]:
    regular_stat(path)
    result: Dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        key, separator, value = raw.partition("=")
        if not separator or not key or key in result:
            raise AuditError(f"{path}:{line_number}: malformed/duplicate key")
        result[key] = value
    return result


def positive_integer(value: Any, context: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise AuditError(f"{context}: invalid integer {value!r}") from exc
    if result <= 0 or str(result) != str(value):
        raise AuditError(f"{context}: expected canonical positive integer")
    return result


def parse_manifest(path: Path) -> list[tuple[str, int]]:
    regular_stat(path)
    if sha256(path) != EXPECTED_MANIFEST_SHA256:
        raise AuditError(f"manifest SHA-256 differs from exact official inventory: {path}")
    rows: list[tuple[str, int]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = raw.split("\t")
        expected = f"Y13718.{number}.al"
        if len(fields) != 2 or fields[0] != expected:
            raise AuditError(f"{path}:{number}: expected {expected} and one byte count")
        rows.append((fields[0][:-3], positive_integer(fields[1], f"{path}:{number}")))
    if len(rows) != EXPECTED_FILES:
        raise AuditError(f"manifest contains {len(rows)} rows, expected {EXPECTED_FILES}")
    if sum(size for _, size in rows) != EXPECTED_INPUT_BYTES:
        raise AuditError("manifest byte total differs from the exact inventory")
    return rows


def require_exact_names(directory: Path, expected: set[str], label: str) -> None:
    try:
        actual = {entry.name for entry in directory.iterdir()}
    except OSError as exc:
        raise AuditError(f"cannot list {label} directory {directory}: {exc}") from exc
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise AuditError(f"{label} inventory differs; missing={missing}, extra={extra}")


def parse_validation_entries(value: str, context: str) -> int:
    try:
        tokens = shlex.split(value)
    except ValueError as exc:
        raise AuditError(f"{context}: malformed validation summary: {exc}") from exc
    fields: Dict[str, str] = {}
    for token in tokens:
        key, separator, item = token.partition("=")
        if not separator or not key or key in fields:
            raise AuditError(f"{context}: malformed validation token {token!r}")
        fields[key] = item
    for key, wanted in (
        ("status", "PASS"),
        ("btag_mode", "recalc"),
        ("recalculated_expected", "1"),
        ("failures", "0"),
        ("identity_failures", "0"),
        ("frame_read_failures", "0"),
    ):
        if fields.get(key) != wanted:
            raise AuditError(f"{context}: {key}={fields.get(key)!r}, expected {wanted!r}")
    return positive_integer(fields.get("entries"), f"{context}.entries")


def marker_events(
    path: Path,
    *,
    phase: str,
    tape: str,
    input_size: int,
    output: Path,
    campaign_sha: str,
    audit: Path | None,
) -> int:
    values = load_key_values(path)
    expected = {
        "format": "delphi-lolept94-c2-complete-v1",
        "phase": phase,
        "tape": tape,
        "input_size_bytes": str(input_size),
        "output": output.name,
        "output_size_bytes": str(regular_stat(output).st_size),
        "btag_mode": "recalc",
        "recalculated": "1",
        "campaign_sha256": campaign_sha,
        "identity_check": (
            "exact-ordered-run-event-fileSeq" if phase == "final" else "not-applicable"
        ),
    }
    for key, wanted in expected.items():
        if values.get(key) != wanted:
            raise AuditError(f"{path}: {key}={values.get(key)!r}, expected {wanted!r}")
    if audit is None:
        if values.get("lepton_schema_audit_sha256") != "not-run":
            raise AuditError(f"{path}: intermediate unexpectedly claims lepton audit")
    elif values.get("lepton_schema_audit_sha256") != sha256(audit):
        raise AuditError(f"{path}: lepton audit digest differs")
    events = positive_integer(values.get("events"), f"{path}:events")
    if parse_validation_entries(values.get("validation", ""), f"{path}:validation") != events:
        raise AuditError(f"{path}: validation entry count differs")
    return events


def audit_quarantines(campaign: Path) -> Dict[str, Any]:
    root = campaign / "interrupted"
    if root.is_symlink() or not root.is_dir():
        raise AuditError(f"interrupted quarantine directory is missing: {root}")
    reports = []
    for quarantine in sorted(root.iterdir(), key=lambda item: item.name):
        if quarantine.is_symlink() or not quarantine.is_dir():
            raise AuditError(f"unexpected interrupted inventory entry: {quarantine}")
        manifest = quarantine / "CONTENTS.tsv"
        regular_stat(manifest)
        rows = manifest.read_text(encoding="utf-8").splitlines()
        if not rows or rows[0] != "kind\tsize_bytes\tsha256\toriginal_path\tquarantine_path":
            raise AuditError(f"malformed quarantine manifest: {manifest}")
        files = directories = bytes_total = 0
        for number, raw in enumerate(rows[1:], 2):
            fields = raw.split("\t")
            if len(fields) != 5:
                raise AuditError(f"{manifest}:{number}: expected five fields")
            kind, size_text, digest, _original, recorded_path = fields
            item = Path(recorded_path)
            try:
                item.relative_to(quarantine)
            except ValueError as exc:
                raise AuditError(f"{manifest}:{number}: path escapes quarantine") from exc
            if kind == "file":
                size = regular_stat(item, allow_empty=True).st_size
                if str(size) != size_text or sha256(item) != digest:
                    raise AuditError(f"{manifest}:{number}: quarantined file integrity differs")
                files += 1
                bytes_total += size
            elif kind == "directory":
                if size_text != "-" or digest != "-" or item.is_symlink() or not item.is_dir():
                    raise AuditError(f"{manifest}:{number}: quarantined directory differs")
                directories += 1
            else:
                raise AuditError(f"{manifest}:{number}: unknown kind {kind!r}")
        reports.append(
            {
                "name": quarantine.name,
                "manifest": str(manifest),
                "manifest_sha256": sha256(manifest),
                "recorded_files": files,
                "recorded_directories": directories,
                "recorded_file_bytes": bytes_total,
                "status": "intact",
            }
        )
    return {"count": len(reports), "items": reports, "status": "intact"}


def frame_integer(frame: Any, name: str, context: str) -> int:
    if name not in set(frame.parameters):
        raise AuditError(f"{context}: missing event parameter {name}")
    try:
        return int(frame.get_parameter(name))
    except Exception as exc:
        raise AuditError(f"{context}: cannot read event parameter {name}: {exc}") from exc


def scan_root(task: tuple[str, str, int]) -> Dict[str, Any]:
    tape, path_text, expected_events = task
    path = Path(path_text)
    try:
        from podio import root_io
    except ImportError as exc:
        raise AuditError("podio is unavailable; run inside the pinned Key4hep environment") from exc
    before = path.stat()
    keys: list[tuple[int, int, int]] = []
    try:
        for entry, frame in enumerate(root_io.Reader(str(path)).get("events")):
            context = f"{path}:events[{entry}]"
            keys.append(tuple(frame_integer(frame, name, context) for name in IDENTITY_PARAMETERS))
    except AuditError:
        raise
    except Exception as exc:
        raise AuditError(f"{path}: podio scan failed: {type(exc).__name__}: {exc}") from exc
    after = path.stat()
    fingerprint = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if fingerprint(before) != fingerprint(after):
        raise AuditError(f"{path}: ROOT file changed during scan")
    if len(keys) != expected_events:
        raise AuditError(f"{path}: scanned {len(keys)} events, marker records {expected_events}")
    return {"tape": tape, "path": str(path), "events": len(keys), "keys": keys}


def audit_campaign(campaign: Path, jobs: int) -> Dict[str, Any]:
    campaign = campaign.resolve(strict=True)
    if campaign.is_symlink() or not campaign.is_dir():
        raise AuditError(f"campaign is not a real directory: {campaign}")
    lock_path = campaign / ".campaign.lock"
    regular_stat(lock_path, allow_empty=True)
    lock_stream = lock_path.open("rb")
    try:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AuditError(f"campaign is active: {campaign}") from exc

        config_path = campaign / "campaign.conf"
        manifest_path = campaign / "inputs.manifest.tsv"
        config = load_key_values(config_path)
        for key, wanted in (
            ("format", "delphi-lolept94-c2-recalc-v1"),
            ("dataset", DATASET),
            ("btag_mode", "recalc"),
            ("recalculated", "1"),
            ("file_count", str(EXPECTED_FILES)),
            ("input_bytes", str(EXPECTED_INPUT_BYTES)),
            ("expected_events", str(CATALOG_EVENTS)),
            ("manifest_sha256", EXPECTED_MANIFEST_SHA256),
        ):
            if config.get(key) != wanted:
                raise AuditError(f"{config_path}: {key}={config.get(key)!r}, expected {wanted!r}")
        rows = parse_manifest(manifest_path)
        campaign_sha = sha256(config_path)

        tape_names = {tape for tape, _ in rows}
        intermediate_names = {
            name
            for tape in tape_names
            for name in (f"inter_{tape}.root", f"inter_{tape}.root.complete")
        }
        final_names = {
            name
            for tape in tape_names
            for name in (
                f"lolept94_c2_{tape}.edm4hep.root",
                f"lolept94_c2_{tape}.edm4hep.root.complete",
            )
        }
        audit_names = {f"{tape}.lepton_pid.json" for tape in tape_names}
        log_names = {
            f"{tape}.{suffix}"
            for tape in tape_names
            for suffix in (
                "pass1.log",
                "pass1.validation.log",
                "pass2.log",
                "final.validation.log",
                "lepton_pid.log",
            )
        }
        lock_names = {f"{tape}.lock" for tape in tape_names}
        require_exact_names(campaign / "intermediates", intermediate_names, "intermediate")
        require_exact_names(campaign / "edm4hep", final_names, "final")
        require_exact_names(campaign / "audits", audit_names, "lepton audit")
        require_exact_names(campaign / "logs", log_names, "log")
        require_exact_names(campaign / ".locks", lock_names, "per-tape lock")
        if any((campaign / ".scratch").iterdir()):
            raise AuditError(f"live scratch directory is not empty: {campaign / '.scratch'}")

        intermediate_total = final_total = 0
        intermediate_bytes = final_bytes = 0
        scan_tasks = []
        per_tape = []
        for tape, input_size in rows:
            intermediate = campaign / "intermediates" / f"inter_{tape}.root"
            final = campaign / "edm4hep" / f"lolept94_c2_{tape}.edm4hep.root"
            audit = campaign / "audits" / f"{tape}.lepton_pid.json"
            regular_stat(audit)
            try:
                audit_payload = json.loads(audit.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise AuditError(f"cannot decode frozen lepton audit {audit}: {exc}") from exc
            if (
                audit_payload.get("format") != "delphi-edm4hep-lepton-pid-audit-v1"
                or audit_payload.get("status") != "PASS"
                or audit_payload.get("failures", {}).get("count") != 0
            ):
                raise AuditError(f"frozen lepton audit is not PASS with zero failures: {audit}")
            intermediate_events = marker_events(
                Path(f"{intermediate}.complete"),
                phase="intermediate",
                tape=tape,
                input_size=input_size,
                output=intermediate,
                campaign_sha=campaign_sha,
                audit=None,
            )
            final_events = marker_events(
                Path(f"{final}.complete"),
                phase="final",
                tape=tape,
                input_size=input_size,
                output=final,
                campaign_sha=campaign_sha,
                audit=audit,
            )
            if intermediate_events != final_events:
                raise AuditError(f"{tape}: pass-1/pass-2 marker counts differ")
            intermediate_total += intermediate_events
            final_total += final_events
            intermediate_bytes += intermediate.stat().st_size
            final_bytes += final.stat().st_size
            scan_tasks.append((tape, str(final), final_events))
            per_tape.append({"tape": tape, "events": final_events})
        if intermediate_total != EXPECTED_PAYLOAD_EVENTS or final_total != EXPECTED_PAYLOAD_EVENTS:
            raise AuditError(
                f"pass totals are {intermediate_total}/{final_total}, "
                f"expected {EXPECTED_PAYLOAD_EVENTS}"
            )

        full_locations: Dict[tuple[int, int, int], tuple[str, int]] = {}
        full_duplicate_samples = []
        run_event_sequences: Dict[tuple[int, int], set[int]] = defaultdict(set)
        run_numbers: set[int] = set()
        scanned_events = 0
        with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as executor:
            futures = [executor.submit(scan_root, task) for task in scan_tasks]
            for future in concurrent.futures.as_completed(futures):
                item = future.result()
                scanned_events += item["events"]
                for entry, key in enumerate(item["keys"]):
                    previous = full_locations.get(key)
                    if previous is not None and len(full_duplicate_samples) < 20:
                        full_duplicate_samples.append(
                            {
                                "run": key[0],
                                "event": key[1],
                                "file_seq": key[2],
                                "first": {"tape": previous[0], "entry": previous[1]},
                                "repeat": {"tape": item["tape"], "entry": entry},
                            }
                        )
                    else:
                        full_locations[key] = (item["tape"], entry)
                    run_event_sequences[(key[0], key[1])].add(key[2])
                    run_numbers.add(key[0])
        if scanned_events != EXPECTED_PAYLOAD_EVENTS:
            raise AuditError(f"payload scan found {scanned_events} events")
        full_duplicates = scanned_events - len(full_locations)
        if full_duplicates != 0:
            raise AuditError(f"payload has {full_duplicates} duplicate full event identities")
        repeated = {
            key: sorted(sequences)
            for key, sequences in run_event_sequences.items()
            if len(sequences) > 1
        }
        repeated_occurrences = scanned_events - len(run_event_sequences)

        quarantine = audit_quarantines(campaign)
        return {
            "format": REPORT_FORMAT,
            "status": "PASS",
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "dataset": DATASET,
            "campaign": str(campaign),
            "acceptance": {
                "payload_event_expectation": EXPECTED_PAYLOAD_EVENTS,
                "catalog_event_count": CATALOG_EVENTS,
                "catalog_event_discrepancy": EXPECTED_PAYLOAD_EVENTS - CATALOG_EVENTS,
                "catalog_event_count_role": "metadata-not-payload-acceptance",
            },
            "inventory": {
                "manifest_files": len(rows),
                "manifest_input_bytes": sum(size for _, size in rows),
                "manifest_sha256": sha256(manifest_path),
                "campaign_config_sha256": campaign_sha,
                "intermediate_root_files": len(rows),
                "intermediate_completion_markers": len(rows),
                "intermediate_root_bytes": intermediate_bytes,
                "intermediate_marker_events": intermediate_total,
                "final_root_files": len(rows),
                "final_completion_markers": len(rows),
                "final_lepton_audits": len(rows),
                "campaign_logs": len(log_names),
                "per_tape_locks": len(lock_names),
                "final_root_bytes": final_bytes,
                "final_marker_events": final_total,
                "live_scratch_entries": 0,
                "live_temporary_products": 0,
            },
            "event_identity": {
                "identity": ["runNumber", "eventNumber", "fileSeq"],
                "scanned_events": scanned_events,
                "unique_full_keys": len(full_locations),
                "duplicate_full_key_occurrences": full_duplicates,
                "duplicate_full_key_samples": full_duplicate_samples,
                "unique_run_event_keys": len(run_event_sequences),
                "run_event_repeat_groups_with_distinct_file_seq": len(repeated),
                "run_event_repeat_occurrences_beyond_first": repeated_occurrences,
                "run_event_repeat_samples": [
                    {"run": key[0], "event": key[1], "file_seq_values": sequences}
                    for key, sequences in sorted(repeated.items())[:20]
                ],
                "unique_runs": len(run_numbers),
            },
            "quarantine": quarantine,
            "per_tape": per_tape,
        }
    finally:
        lock_stream.close()


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path, help="frozen lolept94_c2 campaign")
    parser.add_argument("--output", type=Path, help="supplemental JSON report")
    parser.add_argument("--jobs", type=int, default=1, help="parallel ROOT readers (1..8)")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.jobs <= 8:
        print(f"ERROR: --jobs must be in 1..8 (got {args.jobs})", file=sys.stderr)
        return 2
    campaign = args.campaign.expanduser().resolve(strict=False)
    reserved = campaign / "supplemental_reports" / "lolept94_c2_event_inventory.json"
    requested = lexical_absolute(args.output or reserved)
    if requested == reserved and not reserved.parent.exists():
        reserved.parent.mkdir(mode=0o755)
    try:
        output = validate_report_destination(
            requested,
            protected_files=(Path(__file__).resolve(),),
            root_policies=((campaign, (reserved,)),),
        )
        report = audit_campaign(campaign, args.jobs)
        payload = json.dumps(canonicalize(report), indent=2, allow_nan=False) + "\n"
        atomic_write_report_text(output, payload)
    except (AuditError, OSError, ReportDestinationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"status=PASS files={report['inventory']['final_root_files']} "
        f"events={report['event_identity']['scanned_events']} "
        f"unique_full_keys={report['event_identity']['unique_full_keys']} "
        f"unique_run_event={report['event_identity']['unique_run_event_keys']} "
        f"unique_runs={report['event_identity']['unique_runs']} "
        f"report_sha256={sha256(output)} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
