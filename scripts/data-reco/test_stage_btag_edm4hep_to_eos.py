#!/usr/bin/env python3
"""Focused tests for stage_btag_edm4hep_to_eos.py."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("stage_btag_edm4hep_to_eos.py")
SPEC = importlib.util.spec_from_file_location("stage_btag_edm4hep_to_eos", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
stage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = stage
SPEC.loader.exec_module(stage)


class StageBtagEdm4hepToEosTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="btag-eos-stage-test-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def record(path: Path) -> dict[str, object]:
        return {
            "path": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_mtime_ns": path.stat().st_mtime_ns,
        }

    def test_resumes_matching_partial_and_is_idempotent(self) -> None:
        source = self.root / "source.root"
        payload = bytes(range(256)) * 8193
        source.write_bytes(payload)
        destination = self.root / "out/source.root"
        destination.parent.mkdir()
        partial = destination.with_name(".source.root.partial")
        partial.write_bytes(payload[:123_457])

        state = stage.copy_resumable_verified(source, destination, self.record(source))
        self.assertEqual(state, "copied")
        self.assertEqual(destination.read_bytes(), payload)
        self.assertFalse(partial.exists())
        state = stage.copy_resumable_verified(source, destination, self.record(source))
        self.assertEqual(state, "already_verified")

    def test_quarantines_wrong_partial_but_never_wrong_final(self) -> None:
        source = self.root / "source.root"
        source.write_bytes(b"correct payload")
        destination = self.root / "out/source.root"
        destination.parent.mkdir()
        partial = destination.with_name(".source.root.partial")
        partial.write_bytes(b"wrong")

        stage.copy_resumable_verified(source, destination, self.record(source))
        self.assertEqual(destination.read_bytes(), b"correct payload")
        self.assertEqual(len(list(destination.parent.glob("*.quarantine.*"))), 1)

        destination.write_bytes(b"wrong final")
        with self.assertRaises(stage.PublishError):
            stage.copy_resumable_verified(source, destination, self.record(source))
        self.assertEqual(destination.read_bytes(), b"wrong final")

    def make_collection(self) -> tuple[object, Path]:
        source_directory = self.root / "source"
        source_directory.mkdir()
        records = []
        total = 0
        for number, payload in enumerate((b"first root", b"second root"), start=1):
            path = source_directory / f"test_{number}.root"
            path.write_bytes(payload)
            path.with_name(path.name + ".complete").write_text(
                "status=PASS\n", encoding="utf-8"
            )
            digest = hashlib.sha256(payload).hexdigest()
            records.append(
                {
                    "root": path.name,
                    "size_bytes": len(payload),
                    "root_sha256": digest,
                }
            )
            total += len(payload)
        audit = source_directory / "audit.json"
        audit.write_text(
            json.dumps({"status": "PASS", "files": records}) + "\n",
            encoding="utf-8",
        )
        collection = stage.Collection(
            key="test",
            source_relative="source",
            destination_relative="legacy_four_way/test",
            root_glob="*.root",
            filename_regex=r"test_[0-9]+\.root",
            expected_files=2,
            expected_bytes=total,
            schema_class="test_schema",
            sample="test sample",
            btag_mode="recalc",
            audit_relative="source/audit.json",
        )
        return collection, source_directory

    def test_manifest_publish_completion_last_and_verify(self) -> None:
        collection, _ = self.make_collection()
        destination_root = self.root / "destination"
        result = stage.publish_collection(collection, self.root, destination_root, 2)
        collection_dir = destination_root / collection.destination_relative
        self.assertEqual(result["status"], "PASS")
        self.assertTrue((collection_dir / "_COMPLETE.json").is_file())
        self.assertTrue((collection_dir / "MANIFEST.json").is_file())
        self.assertTrue((collection_dir / "SHA256SUMS").is_file())
        self.assertTrue((collection_dir / "SOURCE_AUDIT.json").is_file())
        verified = stage.verify_collection(collection_dir)
        self.assertEqual(verified["file_count"], 2)

        sums = collection_dir / "SHA256SUMS"
        original_sums = sums.read_bytes()
        sums.write_bytes(b"0" * 64 + b"  test_1.root\n")
        with self.assertRaises(stage.PublishError):
            stage.verify_collection(collection_dir)
        sums.write_bytes(original_sums)

        with self.assertRaises(stage.PublishError):
            stage.safe_basename("../test_1.root")

        (collection_dir / "test_1.root").write_bytes(b"corrupt")
        with self.assertRaises(stage.PublishError):
            stage.verify_collection(collection_dir)
        stage.COLLECTIONS["test"] = collection
        try:
            with self.assertRaises(stage.PublishError):
                stage.release_completion(destination_root, ("test",))
        finally:
            del stage.COLLECTIONS["test"]

    def test_audit_hash_mismatch_blocks_before_copy(self) -> None:
        collection, source_directory = self.make_collection()
        audit = source_directory / "audit.json"
        payload = json.loads(audit.read_text(encoding="utf-8"))
        payload["files"][0]["root_sha256"] = "0" * 64
        audit.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with self.assertRaises(stage.PublishError):
            stage.build_manifest(collection, self.root, 2)

    def test_initialize_archives_without_deleting_and_deprecates_old_doc(self) -> None:
        eos_area = self.root / "eos"
        eos_area.mkdir()
        (eos_area / "PRODUCTION.md").write_text("obsolete\n", encoding="utf-8")
        old_data = eos_area / "stage1_packaged_data"
        old_data.mkdir()
        (old_data / "chunk.root").write_bytes(b"preserve me")
        destination_root = eos_area / "release"

        stage.initialize_eos_area(eos_area, destination_root)
        archived = eos_area / (
            "archive/legacy_stage1_2026-06/datasets/"
            "stage1_packaged_data/chunk.root"
        )
        self.assertEqual(archived.read_bytes(), b"preserve me")
        self.assertFalse(old_data.exists())
        self.assertTrue(
            (eos_area / "archive/legacy_stage1_2026-06/docs/PRODUCTION_OBSOLETE.md")
            .is_file()
        )
        readme = (eos_area / "README.md").read_text(encoding="utf-8")
        self.assertIn("deprecated", readme)
        self.assertIn("nominal v94c/94C2 MC conditions", readme)
        self.assertFalse(
            (destination_root / "current_schema/qqps_recalc/_COMPLETE.json").exists()
        )

    def test_publication_defaults_recalc_and_legacy_bank_needs_archive_gate(self) -> None:
        defaults = stage.parse_args(["plan"])
        self.assertIsNone(defaults.collection)
        self.assertFalse(defaults.archive_legacy_bank_comparison)
        self.assertTrue(
            all(stage.COLLECTIONS[key].btag_mode == "recalc" for key in stage.CURRENT_SCHEMA_COLLECTIONS)
        )
        with self.assertRaises(stage.PublishError):
            stage.main(
                [
                    "plan",
                    "--source-root",
                    str(self.root),
                    "--destination-root",
                    str(self.root / "destination"),
                    "--collection",
                    "data_bank",
                ]
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
