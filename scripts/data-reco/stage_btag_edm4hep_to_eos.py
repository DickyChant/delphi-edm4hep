#!/usr/bin/env python3
"""Publish validated DELPHI b-tagging EDM4hep ROOT collections to EOS.

The publisher is deliberately conservative:

* source inventories and campaign/audit gates are checked before any write;
* SHA-256 is computed for every source ROOT file;
* interrupted copies resume through ``.<name>.partial`` files;
* an existing mismatching destination is never overwritten;
* every destination ROOT file is re-read and SHA-256 checked;
* ``_COMPLETE.json`` is written atomically and last.

Current publication defaults exclusively to recalculated-AABTAG collections.
The 2026-08-24 Data/qqps bank/recalculation comparison predates the explicit
``AlgorithmInvoked``/``Valid`` event parameters and is retained only below
``legacy_four_way`` behind an explicit archival-release acknowledgement.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


FORMAT = "delphi-btag-edm4hep-eos-release-v1"
DEFAULT_DESTINATION = Path(
    "/eos/user/s/sqian/delphi_hadron_tagging/"
    "edm4hep_94c2_btag_validation_2026-08-25"
)
COPY_CHUNK_BYTES = 16 * 1024 * 1024
LEGACY_RELEASE_COLLECTIONS = (
    "data_bank",
    "data_recalc",
    "qqps_bank",
    "qqps_recalc",
)
CURRENT_SCHEMA_COLLECTIONS = ("qqps_current", "pythia8_current")
ARCHIVED_BANK_COLLECTIONS = ("data_bank", "qqps_bank")


@dataclasses.dataclass(frozen=True)
class Collection:
    key: str
    source_relative: str
    destination_relative: str
    root_glob: str
    filename_regex: str
    expected_files: int
    expected_bytes: int | None
    schema_class: str
    sample: str
    btag_mode: str
    audit_relative: str
    audit_kind: str = "json"
    marker_suffix: str | None = ".complete"


COLLECTIONS: Mapping[str, Collection] = {
    "data_bank": Collection(
        key="data_bank",
        source_relative=(
            "delphi-edm4hep/reruns/btag_recalc/legacy_closure/data_full_94c"
        ),
        destination_relative="legacy_four_way/data_bank",
        root_glob="*.root",
        filename_regex=r"inter_Y[0-9]+\.[0-9]+\.root",
        expected_files=429,
        expected_bytes=21_211_508_365,
        schema_class="legacy_no_explicit_algorithm_invoked_or_valid",
        sample="DELPHI 1994C data, 429 tapes",
        btag_mode="bank",
        audit_relative=(
            "delphi-edm4hep/reruns/btag_recalc/legacy_closure/"
            "data_full_94c/AUDIT_SDST_BANK_2026-08-24.json"
        ),
    ),
    "data_recalc": Collection(
        key="data_recalc",
        source_relative=(
            "delphi-edm4hep/reruns/btag_recalc/batch94c/intermediates"
        ),
        destination_relative="legacy_four_way/data_recalc",
        root_glob="*.root",
        filename_regex=r"inter_Y[0-9]+\.[0-9]+\.root",
        expected_files=429,
        expected_bytes=22_925_467_500,
        schema_class="legacy_no_explicit_algorithm_invoked_or_valid",
        sample="DELPHI 1994C data, 429 tapes",
        btag_mode="recalc",
        audit_relative=(
            "delphi-edm4hep/reruns/btag_recalc/batch94c/"
            "AUDIT_SDST_AABTAG_2026-08-24.json"
        ),
    ),
    "qqps_bank": Collection(
        key="qqps_bank",
        source_relative=(
            "delphi-edm4hep/reruns/btag_recalc/legacy_closure/"
            "mc_full_qqps_v94c_91p25"
        ),
        destination_relative="legacy_four_way/qqps_bank",
        root_glob="*.root",
        filename_regex=r"qqps_91\.25_[0-9]+\.edm4hep\.root",
        expected_files=166,
        expected_bytes=6_011_562_836,
        schema_class="legacy_no_explicit_algorithm_invoked_or_valid",
        sample="official DELPHI v94c qqps 91.25 GeV MC, 166 files",
        btag_mode="bank",
        audit_relative=(
            "delphi-edm4hep/reruns/btag_recalc/legacy_closure/"
            "mc_full_qqps_v94c_91p25/AUDIT_QQPS_V94C_91P25_BANK.json"
        ),
    ),
    "qqps_recalc": Collection(
        key="qqps_recalc",
        source_relative=(
            "delphi-edm4hep/reruns/btag_recalc/mc/qqps_v94c_91p25"
        ),
        destination_relative="legacy_four_way/qqps_recalc",
        root_glob="*.root",
        filename_regex=r"qqps_91\.25_[0-9]+\.edm4hep\.root",
        expected_files=166,
        expected_bytes=6_416_380_688,
        schema_class="legacy_no_explicit_algorithm_invoked_or_valid",
        sample="official DELPHI v94c qqps 91.25 GeV MC, 166 files",
        btag_mode="recalc",
        audit_relative=(
            "delphi-edm4hep/reruns/btag_recalc/mc/qqps_v94c_91p25/"
            "AUDIT_QQPS_V94C_91P25_RECALC.json"
        ),
    ),
    "qqps_current": Collection(
        key="qqps_current",
        source_relative=(
            "delphi-edm4hep/reruns/btag_recalc/mc/"
            "qqps_v94c_91p25_current_schema"
        ),
        destination_relative="current_schema/qqps_recalc",
        root_glob="*.root",
        filename_regex=r"qqps_91\.25_[0-9]+\.edm4hep\.root",
        expected_files=166,
        expected_bytes=None,
        schema_class="current_explicit_algorithm_invoked_and_valid",
        sample="official DELPHI v94c qqps 91.25 GeV MC, 166 files",
        btag_mode="recalc",
        audit_relative=(
            "delphi-edm4hep/reruns/btag_recalc/mc/"
            "qqps_v94c_91p25_current_schema/"
            "AUDIT_QQPS_V94C_91P25_RECALC.json"
        ),
    ),
    "pythia8_current": Collection(
        key="pythia8_current",
        source_relative=(
            "delphi-sim-pipeline/controlled_outputs/pythia8_94c2_50k"
        ),
        destination_relative="current_schema/pythia8_recalc",
        root_glob="samples/*/*.recalc.edm4hep.root",
        filename_regex=(
            r"pythia8_default_isron_ecm91p25_seed[0-9]+_5000"
            r"\.recalc\.edm4hep\.root"
        ),
        expected_files=10,
        expected_bytes=None,
        schema_class="current_explicit_algorithm_invoked_and_valid",
        sample="controlled Pythia8 91.25 GeV MC, 10 x 5000 events",
        btag_mode="recalc",
        audit_relative=(
            "delphi-sim-pipeline/controlled_outputs/"
            "pythia8_94c2_50k/campaign.complete"
        ),
        audit_kind="key_value",
        marker_suffix=".aabtag.provenance",
    ),
}


ARCHIVE_MOVES: tuple[tuple[str, str], ...] = (
    ("PRODUCTION.md", "docs/PRODUCTION_OBSOLETE.md"),
    ("report.pdf", "docs/report.pdf"),
    ("plots", "docs/plots"),
    ("stage1_packaged_bhadron", "datasets/stage1_packaged_bhadron"),
    ("stage1_packaged_bhadron_v2", "datasets/stage1_packaged_bhadron_v2"),
    ("stage1_packaged_data", "datasets/stage1_packaged_data"),
    ("stage1_packaged_data_v2", "datasets/stage1_packaged_data_v2"),
    ("stage1_packaged_mc", "datasets/stage1_packaged_mc"),
    ("stage1_packaged_mc_v2", "datasets/stage1_packaged_mc_v2"),
    ("thrust_test", "tests/thrust_test"),
    ("thrust_test_v2", "tests/thrust_test_v2"),
)


class PublishError(RuntimeError):
    """A condition that prevents safe publication."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path, limit: int | None = None) -> str:
    digest = hashlib.sha256()
    remaining = limit
    with path.open("rb") as handle:
        while True:
            size = COPY_CHUNK_BYTES if remaining is None else min(
                COPY_CHUNK_BYTES, remaining
            )
            if size == 0:
                break
            block = handle.read(size)
            if not block:
                break
            digest.update(block)
            if remaining is not None:
                remaining -= len(block)
    if remaining not in (None, 0):
        raise PublishError(f"short read while hashing {path}")
    return digest.hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def safe_basename(value: Any) -> str:
    if not isinstance(value, str) or not value or value in (".", ".."):
        raise PublishError(f"unsafe manifest filename: {value!r}")
    if Path(value).name != value or "/" in value or "\\" in value:
        raise PublishError(f"manifest path is not a basename: {value!r}")
    return value


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if temporary.exists():
        raise PublishError(f"temporary metadata path already exists: {temporary}")
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_key_value(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        key, separator, value = raw.partition("=")
        if not separator or not key or key in result:
            raise PublishError(f"malformed or duplicate field in {path}: {raw!r}")
        result[key] = value
    return result


def audit_status(path: Path, kind: str) -> tuple[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise PublishError(f"required audit/completion gate missing: {path}")
    if kind == "json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        status = payload.get("status")
        if status is None and isinstance(payload.get("audit"), dict):
            status = payload["audit"].get("status")
    elif kind == "key_value":
        payload = read_key_value(path)
        status = payload.get("status")
    else:
        raise PublishError(f"unsupported audit kind: {kind}")
    if status != "PASS":
        raise PublishError(f"audit/completion gate is not PASS: {path}: {status!r}")
    return str(status), payload


def audited_file_map(audit_payload: Any) -> dict[str, dict[str, Any]]:
    """Return per-file qqps audit records when the audit provides them."""
    if not isinstance(audit_payload, dict) or not isinstance(
        audit_payload.get("files"), list
    ):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for record in audit_payload["files"]:
        if not isinstance(record, dict):
            continue
        name = record.get("root") or record.get("output")
        if isinstance(name, str):
            result[Path(name).name] = record
    return result


def source_paths(spec: Collection, source_root: Path) -> list[Path]:
    directory = source_root / spec.source_relative
    if not directory.is_dir() or directory.is_symlink():
        raise PublishError(f"source directory missing or unsafe: {directory}")
    files = sorted(directory.glob(spec.root_glob), key=lambda item: item.name)
    regex = re.compile(spec.filename_regex)
    bad = [str(path) for path in files if not regex.fullmatch(path.name)]
    if bad:
        raise PublishError(f"unexpected ROOT filename(s) for {spec.key}: {bad[:5]}")
    if len(files) != spec.expected_files:
        raise PublishError(
            f"{spec.key}: expected {spec.expected_files} ROOT files, found {len(files)}"
        )
    names = [path.name for path in files]
    if len(set(names)) != len(names):
        raise PublishError(f"{spec.key}: duplicate destination basenames")
    total = sum(path.stat().st_size for path in files)
    if spec.expected_bytes is not None and total != spec.expected_bytes:
        raise PublishError(
            f"{spec.key}: expected {spec.expected_bytes} bytes, found {total}"
        )
    for path in files:
        if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
            raise PublishError(f"unsafe or empty source ROOT file: {path}")
    return files


def marker_for(spec: Collection, source: Path) -> Path | None:
    if spec.marker_suffix is None:
        return None
    if spec.key == "pythia8_current":
        stem = source.name.removesuffix(".root")
        return source.with_name(stem + spec.marker_suffix)
    return source.with_name(source.name + spec.marker_suffix)


def hash_source_record(
    spec: Collection,
    source: Path,
    audit_records: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    before = source.stat()
    digest = sha256_file(source)
    after = source.stat()
    stable_fields = ("st_size", "st_mtime_ns", "st_ino", "st_dev")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise PublishError(f"source changed while hashing: {source}")

    audited = audit_records.get(source.name)
    if audited:
        audited_size = audited.get("size_bytes") or audited.get("output_size_bytes")
        audited_sha = audited.get("root_sha256") or audited.get("output_sha256")
        if audited_size is not None and int(audited_size) != before.st_size:
            raise PublishError(f"audit size mismatch for {source}")
        if audited_sha is not None and audited_sha != digest:
            raise PublishError(f"audit SHA-256 mismatch for {source}")

    marker = marker_for(spec, source)
    marker_record: dict[str, Any] | None = None
    if marker is not None and marker.is_file() and not marker.is_symlink():
        marker_record = {
            "path": str(marker),
            "size_bytes": marker.stat().st_size,
            "sha256": sha256_file(marker),
        }
        if spec.key == "pythia8_current":
            fields = read_key_value(marker)
            if fields.get("status") != "PASS":
                raise PublishError(f"Pythia shard provenance is not PASS: {marker}")
            if fields.get("output_sha256") != digest:
                raise PublishError(
                    f"Pythia shard provenance output hash mismatch: {marker}"
                )

    return {
        "path": source.name,
        "size_bytes": before.st_size,
        "sha256": digest,
        "source_mtime_ns": before.st_mtime_ns,
        "source_completion_marker": marker_record,
    }


def build_manifest(
    spec: Collection, source_root: Path, workers: int
) -> tuple[dict[str, Any], Path]:
    files = source_paths(spec, source_root)
    audit = source_root / spec.audit_relative
    status, audit_payload = audit_status(audit, spec.audit_kind)
    audit_records = audited_file_map(audit_payload)
    if audit_records and len(audit_records) != spec.expected_files:
        raise PublishError(
            f"{spec.key}: audit has {len(audit_records)} file records; "
            f"expected {spec.expected_files}"
        )

    print(
        f"[{spec.key}] hashing {len(files)} source ROOT files with "
        f"{workers} worker(s)",
        flush=True,
    )
    records: list[dict[str, Any]] = []
    progress = 0
    progress_lock = threading.Lock()

    def hash_one(path: Path) -> dict[str, Any]:
        nonlocal progress
        record = hash_source_record(spec, path, audit_records)
        with progress_lock:
            progress += 1
            if progress % 25 == 0 or progress == len(files):
                print(f"[{spec.key}] source hashes {progress}/{len(files)}", flush=True)
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(hash_one, files))
    records.sort(key=lambda record: record["path"])
    total_bytes = sum(int(record["size_bytes"]) for record in records)
    sha_lines = "".join(
        f"{record['sha256']}  {record['path']}\n" for record in records
    ).encode("utf-8")
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "collection": spec.key,
        "schema_class": spec.schema_class,
        "sample": spec.sample,
        "btag_mode": spec.btag_mode,
        "created_utc": utc_now(),
        "created_host": socket.getfqdn(),
        "source_directory": str(source_root / spec.source_relative),
        "source_audit": {
            "path": str(audit),
            "kind": spec.audit_kind,
            "status": status,
            "size_bytes": audit.stat().st_size,
            "sha256": sha256_file(audit),
        },
        "inventory": {
            "file_count": len(records),
            "total_bytes": total_bytes,
            "sha256sums_sha256": hashlib.sha256(sha_lines).hexdigest(),
            "source_markers_present": sum(
                record["source_completion_marker"] is not None for record in records
            ),
        },
        "files": records,
    }
    return manifest, audit


def compare_prefix(source: Path, partial: Path) -> bool:
    size = partial.stat().st_size
    with source.open("rb") as left, partial.open("rb") as right:
        remaining = size
        while remaining:
            count = min(COPY_CHUNK_BYTES, remaining)
            left_block = left.read(count)
            right_block = right.read(count)
            if left_block != right_block or len(left_block) != count:
                return False
            remaining -= count
    return True


def quarantine(path: Path, reason: str) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.quarantine.{stamp}.{os.getpid()}")
    os.replace(path, target)
    print(f"quarantined {reason}: {path} -> {target}", flush=True)
    return target


def copy_resumable_verified(source: Path, destination: Path, record: Mapping[str, Any]) -> str:
    expected_size = int(record["size_bytes"])
    expected_sha = str(record["sha256"])
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        if destination.is_symlink() or not destination.is_file():
            raise PublishError(f"unsafe existing destination: {destination}")
        if destination.stat().st_size == expected_size and sha256_file(destination) == expected_sha:
            return "already_verified"
        raise PublishError(
            f"existing destination differs; refusing to overwrite: {destination}"
        )

    partial = destination.with_name(f".{destination.name}.partial")
    if partial.exists():
        if partial.is_symlink() or not partial.is_file():
            raise PublishError(f"unsafe partial destination: {partial}")
        if partial.stat().st_size > expected_size or not compare_prefix(source, partial):
            quarantine(partial, "nonmatching partial copy")

    copied = partial.stat().st_size if partial.exists() else 0
    mode = "ab" if copied else "xb"
    with source.open("rb") as input_handle, partial.open(mode) as output_handle:
        input_handle.seek(copied)
        while True:
            block = input_handle.read(COPY_CHUNK_BYTES)
            if not block:
                break
            output_handle.write(block)
        output_handle.flush()
        os.fsync(output_handle.fileno())

    if partial.stat().st_size != expected_size or sha256_file(partial) != expected_sha:
        raise PublishError(f"copied payload does not match source manifest: {partial}")
    source_stat = source.stat()
    if (
        source_stat.st_size != expected_size
        or source_stat.st_mtime_ns != int(record["source_mtime_ns"])
        or sha256_file(source) != expected_sha
    ):
        raise PublishError(f"source changed during copy: {source}")
    os.replace(partial, destination)
    return "copied"


def publish_collection(
    spec: Collection,
    source_root: Path,
    destination_root: Path,
    workers: int,
) -> dict[str, Any]:
    manifest, audit = build_manifest(spec, source_root, workers)
    collection_dir = destination_root / spec.destination_relative
    completion = collection_dir / "_COMPLETE.json"
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    if completion.exists():
        print(f"[{spec.key}] completion marker exists; verify-only", flush=True)
        return verify_collection(collection_dir, spec)

    collection_dir.mkdir(parents=True, exist_ok=True)
    source_directory = source_root / spec.source_relative
    copied = 0
    reused = 0
    for index, record in enumerate(manifest["files"], start=1):
        source = next(source_directory.glob("**/" + str(record["path"])), None)
        if source is None:
            raise PublishError(f"manifest source disappeared: {record['path']}")
        state = copy_resumable_verified(
            source, collection_dir / str(record["path"]), record
        )
        copied += state == "copied"
        reused += state == "already_verified"
        if index % 25 == 0 or index == len(manifest["files"]):
            print(
                f"[{spec.key}] staged {index}/{len(manifest['files'])} "
                f"(copied={copied}, reused={reused})",
                flush=True,
            )

    sha_lines = "".join(
        f"{record['sha256']}  {record['path']}\n" for record in manifest["files"]
    ).encode("utf-8")
    atomic_write(collection_dir / "MANIFEST.json", manifest_bytes)
    atomic_write(collection_dir / "SHA256SUMS", sha_lines)
    atomic_write(
        collection_dir / f"SOURCE_AUDIT{audit.suffix}", audit.read_bytes()
    )

    print(f"[{spec.key}] re-hashing EOS destination", flush=True)
    for index, record in enumerate(manifest["files"], start=1):
        destination = collection_dir / str(record["path"])
        if (
            destination.stat().st_size != int(record["size_bytes"])
            or sha256_file(destination) != record["sha256"]
        ):
            raise PublishError(f"destination verification failed: {destination}")
        if index % 25 == 0 or index == len(manifest["files"]):
            print(
                f"[{spec.key}] destination hashes {index}/{len(manifest['files'])}",
                flush=True,
            )

    complete_payload = {
        "format": FORMAT,
        "status": "PASS",
        "collection": spec.key,
        "schema_class": spec.schema_class,
        "file_count": manifest["inventory"]["file_count"],
        "total_bytes": manifest["inventory"]["total_bytes"],
        "manifest_sha256": manifest_sha,
        "sha256sums_sha256": manifest["inventory"]["sha256sums_sha256"],
        "destination_verified_utc": utc_now(),
    }
    atomic_write(completion, canonical_json_bytes(complete_payload))
    print(f"[{spec.key}] PASS: {completion}", flush=True)
    return complete_payload


def verify_collection(
    collection_dir: Path, expected_spec: Collection | None = None
) -> dict[str, Any]:
    manifest_path = collection_dir / "MANIFEST.json"
    completion_path = collection_dir / "_COMPLETE.json"
    if (
        not manifest_path.is_file()
        or manifest_path.is_symlink()
        or not completion_path.is_file()
        or completion_path.is_symlink()
    ):
        raise PublishError(f"incomplete published collection: {collection_dir}")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT or completion.get("format") != FORMAT:
        raise PublishError(f"unsupported publication format: {collection_dir}")
    if completion.get("status") != "PASS":
        raise PublishError(f"completion status is not PASS: {completion_path}")
    if completion.get("manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest():
        raise PublishError(f"completion/manifest hash mismatch: {collection_dir}")
    if (
        completion.get("collection") != manifest.get("collection")
        or completion.get("schema_class") != manifest.get("schema_class")
    ):
        raise PublishError(f"completion/manifest identity mismatch: {collection_dir}")
    if expected_spec is not None and (
        manifest.get("collection") != expected_spec.key
        or manifest.get("schema_class") != expected_spec.schema_class
        or manifest.get("btag_mode") != expected_spec.btag_mode
    ):
        raise PublishError(f"publication does not match expected collection: {collection_dir}")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise PublishError(f"manifest has no files list: {manifest_path}")
    if any(not isinstance(record, dict) for record in files):
        raise PublishError(f"manifest contains a non-object file record: {manifest_path}")
    inventory = manifest.get("inventory")
    if not isinstance(inventory, dict):
        raise PublishError(f"manifest has no inventory: {manifest_path}")
    expected_names = [safe_basename(record.get("path")) for record in files]
    if len(set(expected_names)) != len(expected_names):
        raise PublishError(f"duplicate manifest filename: {manifest_path}")
    actual_root_entries = list(collection_dir.glob("*.root"))
    if any(path.is_symlink() or not path.is_file() for path in actual_root_entries):
        raise PublishError(f"published ROOT set contains an unsafe entry: {collection_dir}")
    actual_names = {path.name for path in actual_root_entries}
    if actual_names != set(expected_names):
        raise PublishError(f"published ROOT set differs from manifest: {collection_dir}")

    expected_sha_lines = "".join(
        f"{record['sha256']}  {safe_basename(record.get('path'))}\n"
        for record in files
    ).encode("utf-8")
    sums_path = collection_dir / "SHA256SUMS"
    if not sums_path.is_file() or sums_path.is_symlink():
        raise PublishError(f"SHA256SUMS missing or unsafe: {sums_path}")
    sums_bytes = sums_path.read_bytes()
    sums_digest = hashlib.sha256(sums_bytes).hexdigest()
    if sums_bytes != expected_sha_lines or sums_digest != inventory.get(
        "sha256sums_sha256"
    ) or sums_digest != completion.get("sha256sums_sha256"):
        raise PublishError(f"SHA256SUMS binding mismatch: {collection_dir}")

    source_audit = manifest.get("source_audit")
    if not isinstance(source_audit, dict) or source_audit.get("status") != "PASS":
        raise PublishError(f"source audit binding missing: {manifest_path}")
    source_audit_suffix = Path(str(source_audit.get("path", ""))).suffix
    if not source_audit_suffix:
        raise PublishError(f"source audit suffix missing: {manifest_path}")
    copied_audit = collection_dir / f"SOURCE_AUDIT{source_audit_suffix}"
    if not copied_audit.is_file() or copied_audit.is_symlink():
        raise PublishError(f"bound source audit missing or unsafe: {copied_audit}")
    if (
        copied_audit.stat().st_size != int(source_audit.get("size_bytes", -1))
        or sha256_file(copied_audit) != source_audit.get("sha256")
    ):
        raise PublishError(f"bound source audit mismatch: {copied_audit}")

    total_bytes = 0
    for index, (record, name) in enumerate(zip(files, expected_names), start=1):
        path = collection_dir / name
        if path.is_symlink() or not path.is_file():
            raise PublishError(f"published ROOT file missing or unsafe: {path}")
        size = path.stat().st_size
        if size != int(record["size_bytes"]) or sha256_file(path) != record["sha256"]:
            raise PublishError(f"published ROOT file mismatch: {path}")
        total_bytes += size
        if index % 25 == 0 or index == len(files):
            print(f"[verify] {collection_dir.name} {index}/{len(files)}", flush=True)
    if (
        len(files) != inventory.get("file_count")
        or total_bytes != inventory.get("total_bytes")
        or len(files) != completion.get("file_count")
        or total_bytes != completion.get("total_bytes")
    ):
        raise PublishError(f"published aggregate mismatch: {collection_dir}")
    return completion


def top_readme(destination_name: str) -> bytes:
    return f"""# DELPHI hadron-tagging EOS area

The event-level EDM4hep b-tag validation release is in `{destination_name}/`.
Only consume a collection when its `_COMPLETE.json` exists with `status=PASS`;
the accompanying `MANIFEST.json` and `SHA256SUMS` bind every ROOT file.

`legacy_four_way/` contains the complete Data/qqps x bank/recalculated
comparison.  These files predate the explicit AABTAG `AlgorithmInvoked` and
`Valid` event parameters and must not be described as current-schema files.

`current_schema/` is reserved for the refreshed qqps reference and controlled
Pythia8 sample with the explicit validity contract.  A reserved directory is
not a dataset and has no completion marker until its campaign and EOS hashes
both pass.

Older NanoAOD/chunked stage-1 material and the obsolete `PRODUCTION.md` are
preserved, without deletion, in `archive/legacy_stage1_2026-06/`.  The old
document's suggestion to inject a Data per-tape beamspot into MC is deprecated:
the controlled MC path uses the nominal v94c/94C2 MC conditions and records its
run/seed mapping in campaign provenance.
""".encode("utf-8")


def initialize_eos_area(eos_area: Path, destination_root: Path) -> None:
    archive = eos_area / "archive/legacy_stage1_2026-06"
    moves: list[dict[str, str]] = []
    for source_name, archive_relative in ARCHIVE_MOVES:
        source = eos_area / source_name
        target = archive / archive_relative
        if source.exists() or source.is_symlink():
            if target.exists() or target.is_symlink():
                raise PublishError(
                    f"both live and archive paths exist; refusing ambiguous move: "
                    f"{source} and {target}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            print(f"archived: {source} -> {target}", flush=True)
        if target.exists():
            moves.append({"original": str(source), "archived": str(target)})

    archive_index = {
        "format": "delphi-hadron-tagging-recoverable-archive-v1",
        "status": "PRESERVED_NOT_DELETED",
        "created_utc": utc_now(),
        "entries": moves,
    }
    atomic_write(archive / "_ARCHIVE_INDEX.json", canonical_json_bytes(archive_index))
    atomic_write(eos_area / "README.md", top_readme(destination_root.name))

    for relative in (
        "legacy_four_way/data_bank",
        "legacy_four_way/data_recalc",
        "legacy_four_way/qqps_bank",
        "legacy_four_way/qqps_recalc",
        "current_schema/qqps_recalc",
        "current_schema/pythia8_recalc",
        "manifests",
        "results",
    ):
        (destination_root / relative).mkdir(parents=True, exist_ok=True)
    current_note = (
        "Reserved for verified current-schema products. This directory is not "
        "a dataset until its collection-level _COMPLETE.json exists.\n"
    ).encode("utf-8")
    atomic_write(destination_root / "current_schema/README.txt", current_note)


def release_completion(
    destination_root: Path,
    collection_keys: Sequence[str],
) -> None:
    entries = []
    for key in collection_keys:
        spec = COLLECTIONS[key]
        collection_dir = destination_root / spec.destination_relative
        completion_path = collection_dir / "_COMPLETE.json"
        completion = verify_collection(collection_dir, spec)
        entries.append(
            {
                "collection": key,
                "path": spec.destination_relative,
                "completion_sha256": sha256_file(completion_path),
                "file_count": completion["file_count"],
                "total_bytes": completion["total_bytes"],
                "manifest_sha256": completion["manifest_sha256"],
            }
        )
    payload = {
        "format": FORMAT,
        "status": "PASS",
        "release": "legacy_four_way",
        "schema_class": "legacy_no_explicit_algorithm_invoked_or_valid",
        "created_utc": utc_now(),
        "file_count": sum(entry["file_count"] for entry in entries),
        "total_bytes": sum(entry["total_bytes"] for entry in entries),
        "collections": entries,
    }
    manifest_path = destination_root / "manifests/legacy_four_way_RELEASE.json"
    atomic_write(manifest_path, canonical_json_bytes(payload))
    payload["release_manifest_sha256"] = sha256_file(manifest_path)
    atomic_write(
        destination_root / "legacy_four_way/_COMPLETE.json",
        canonical_json_bytes(payload),
    )


def print_plan(source_root: Path, destination_root: Path, keys: Iterable[str]) -> None:
    print(f"source_root={source_root}")
    print(f"destination_root={destination_root}")
    for key in keys:
        spec = COLLECTIONS[key]
        directory = source_root / spec.source_relative
        found = list(directory.glob(spec.root_glob)) if directory.is_dir() else []
        total = sum(path.stat().st_size for path in found if path.is_file())
        audit = source_root / spec.audit_relative
        print(
            f"collection={key} schema={spec.schema_class} "
            f"found={len(found)}/{spec.expected_files} bytes={total} "
            f"audit_present={audit.is_file()} "
            f"destination={destination_root / spec.destination_relative}"
        )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("plan", "initialize", "stage", "verify", "all")
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="workspace containing delphi-edm4hep and delphi-sim-pipeline",
    )
    parser.add_argument(
        "--destination-root", type=Path, default=DEFAULT_DESTINATION
    )
    parser.add_argument(
        "--eos-area",
        type=Path,
        default=Path("/eos/user/s/sqian/delphi_hadron_tagging"),
    )
    parser.add_argument(
        "--collection",
        action="append",
        choices=tuple(COLLECTIONS),
        help=(
            "repeat to select collections; current recalculated-AABTAG "
            "collections are the default"
        ),
    )
    parser.add_argument(
        "--archive-legacy-bank-comparison",
        action="store_true",
        help=(
            "required to select a stored-bank legacy_four_way collection; "
            "never use for current production publication"
        ),
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="required for initialize, stage, or all writes",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.workers < 1 or args.workers > 16:
        raise PublishError("--workers must be between 1 and 16")
    source_root = args.source_root.resolve()
    destination_root = args.destination_root
    selected = tuple(args.collection or CURRENT_SCHEMA_COLLECTIONS)
    selected_archived_bank = sorted(set(selected) & set(ARCHIVED_BANK_COLLECTIONS))
    if selected_archived_bank and not args.archive_legacy_bank_comparison:
        raise PublishError(
            "stored-bank collections are archived historical evidence; pass "
            "--archive-legacy-bank-comparison to acknowledge that scope: "
            + ", ".join(selected_archived_bank)
        )

    print_plan(source_root, destination_root, selected)
    if args.action == "plan":
        return 0
    if args.action in ("initialize", "stage", "all") and not args.execute:
        raise PublishError(f"{args.action} is a write action; pass --execute")

    if args.action in ("initialize", "all"):
        initialize_eos_area(args.eos_area, destination_root)
    if args.action in ("stage", "all"):
        for key in selected:
            publish_collection(
                COLLECTIONS[key], source_root, destination_root, args.workers
            )
        if tuple(selected) == LEGACY_RELEASE_COLLECTIONS:
            release_completion(destination_root, selected)
    if args.action == "verify":
        for key in selected:
            spec = COLLECTIONS[key]
            verify_collection(destination_root / spec.destination_relative, spec)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, PublishError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
