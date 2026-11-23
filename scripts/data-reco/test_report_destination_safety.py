#!/usr/bin/env python3
"""Destructive-regression tests for audit/report destination isolation."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


destinations = load("report_destination", "report_destination.py")
data_audit = load("audit_sdst_data_recalc_94c", "audit_sdst_data_recalc_94c.py")
mc_audit = load("audit_sdst_mc_campaign", "audit_sdst_mc_campaign.py")
lepton_summary = load(
    "summarize_lepton_pid_campaign", "summarize_lepton_pid_campaign.py"
)
comparison = load("compare_aabtag_recalc", "compare_aabtag_recalc.py")


def quiet_main(function, arguments: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
        io.StringIO()
    ):
        return function(arguments)


class DestinationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.campaign = self.root / "campaign"
        self.source = self.root / "source"
        self.external = self.root / "reports"
        for directory in (self.campaign, self.source, self.external):
            directory.mkdir()
        self.control = self.campaign / "campaign.conf"
        self.control.write_bytes(b"CAMPAIGN-CONTROL\n")
        self.source_file = self.source / "input.sdst"
        self.source_file.write_bytes(b"SOURCE-PAYLOAD\n")
        self.reserved = self.campaign / "AUDIT_RESERVED.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self, output: Path) -> Path:
        return destinations.validate_report_destination(
            output,
            protected_files=(self.control, self.source_file),
            root_policies=(
                (self.campaign, (self.reserved,)),
                (self.source, ()),
            ),
        )

    def test_only_reserved_campaign_location_is_allowed(self) -> None:
        self.assertEqual(self.validate(self.reserved), self.reserved)
        with self.assertRaises(destinations.ReportDestinationError):
            self.validate(self.campaign / "another.json")
        nested = self.campaign / "logs"
        nested.mkdir()
        with self.assertRaises(destinations.ReportDestinationError):
            self.validate(nested / self.reserved.name)
        with self.assertRaises(destinations.ReportDestinationError):
            self.validate(self.source / "report.json")

    def test_raw_parent_symlink_and_final_symlink_are_rejected(self) -> None:
        campaign_alias = self.root / "campaign-alias"
        campaign_alias.symlink_to(self.campaign, target_is_directory=True)
        with self.assertRaises(destinations.ReportDestinationError):
            self.validate(campaign_alias / "another.json")

        final_alias = self.external / "report.json"
        final_alias.symlink_to(self.control)
        with self.assertRaises(destinations.ReportDestinationError):
            self.validate(final_alias)
        self.assertEqual(self.control.read_bytes(), b"CAMPAIGN-CONTROL\n")

        dangling_alias = self.external / "dangling.json"
        dangling_alias.symlink_to(self.root / "does-not-exist")
        with self.assertRaises(destinations.ReportDestinationError):
            self.validate(dangling_alias)

    def test_external_hardlink_alias_is_rejected_without_mutation(self) -> None:
        hardlink = self.external / "report.json"
        os.link(self.control, hardlink)
        before = self.control.stat()
        with self.assertRaises(destinations.ReportDestinationError):
            self.validate(hardlink)
        after = self.control.stat()
        self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
        self.assertEqual(hardlink.read_bytes(), b"CAMPAIGN-CONTROL\n")

    def test_tree_scan_rejects_hardlink_not_named_as_explicit_input(self) -> None:
        nested = self.campaign / "logs"
        nested.mkdir()
        evidence = nested / "validation.log"
        evidence.write_bytes(b"VALIDATION-EVIDENCE\n")
        hardlink = self.external / "report.json"
        os.link(evidence, hardlink)
        with self.assertRaises(destinations.ReportDestinationError):
            self.validate(hardlink)
        self.assertEqual(evidence.read_bytes(), b"VALIDATION-EVIDENCE\n")
        self.assertEqual(hardlink.read_bytes(), b"VALIDATION-EVIDENCE\n")

    def test_nonregular_and_missing_parent_are_rejected(self) -> None:
        fifo = self.external / "report.fifo"
        os.mkfifo(fifo)
        with self.assertRaises(destinations.ReportDestinationError):
            self.validate(fifo)
        missing = self.root / "missing" / "report.json"
        with self.assertRaises(destinations.ReportDestinationError):
            self.validate(missing)
        self.assertFalse(missing.parent.exists())

    def test_descriptor_relative_atomic_replacement(self) -> None:
        report = self.external / "report.json"
        report.write_text("old\n", encoding="utf-8")
        validated = self.validate(report)
        destinations.atomic_write_report_text(validated, "new\n")
        self.assertEqual(report.read_text(encoding="utf-8"), "new\n")
        self.assertEqual(list(self.external.glob(".report.json.*.tmp")), [])


class EntrypointDestructiveRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.campaign = self.root / "campaign"
        self.source = self.root / "source"
        self.campaign.mkdir()
        self.source.mkdir()
        self.control = self.campaign / "campaign.conf"
        self.sentinel = b"DO-NOT-OVERWRITE\n"
        self.control.write_bytes(self.sentinel)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assert_control_preserved(self) -> None:
        self.assertEqual(self.control.read_bytes(), self.sentinel)

    def test_data_audit_rejects_failure_report_over_campaign_input(self) -> None:
        result = quiet_main(
            data_audit.main,
            [str(self.campaign), "--output", str(self.control)],
        )
        self.assertEqual(result, 2)
        self.assert_control_preserved()

    def test_data_audit_refuses_external_output_when_source_root_is_unknown(self) -> None:
        unknown_source = self.root / "unknown-source" / "input.al"
        unknown_source.parent.mkdir()
        unknown_source.write_bytes(self.sentinel)
        result = quiet_main(
            data_audit.main,
            [str(self.campaign), "--output", str(unknown_source)],
        )
        self.assertEqual(result, 2)
        self.assertEqual(unknown_source.read_bytes(), self.sentinel)

    def test_data_audit_rejects_source_tree_after_config_discovery(self) -> None:
        tape_base = self.root / "tapes"
        source = tape_base / "Y1" / "Y1.1.al"
        source.parent.mkdir(parents=True)
        source.write_bytes(self.sentinel)
        worklist = self.campaign / "worklist.txt"
        worklist.write_text("ED1.1 1 Y1.1\n", encoding="utf-8")
        (self.campaign / "worklist.run").write_bytes(worklist.read_bytes())
        al_all = self.campaign / "al.all"
        al_all.write_text("Y1.1\n", encoding="utf-8")
        (self.campaign / "al.run").write_bytes(al_all.read_bytes())
        (self.campaign / ".campaign.lock").touch()
        self.control.write_text(
            "\n".join(
                (
                    "format=delphi-batch94c-v3",
                    "btag_mode=recalc",
                    "primary_vertex_policy=keep-delana",
                    f"worklist={worklist}",
                    "worklist_sha256=invalid-for-this-test",
                    "key4hep_release=test",
                    f"edmbin={self.root / 'bin'}",
                    "sdst_binary_sha256=test",
                    "fdst_binary_sha256=test",
                    "btag_checker_sha256=test",
                    "image=test",
                    f"raw_base={self.root / 'raw'}",
                    f"tape_base={tape_base}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        result = quiet_main(
            data_audit.main,
            [str(self.campaign), "--output", str(source)],
        )
        self.assertEqual(result, 2)
        self.assertEqual(source.read_bytes(), self.sentinel)

    def test_mc_audit_rejects_before_refresh_or_failure_report(self) -> None:
        with mock.patch.object(mc_audit, "refresh_checker_evidence") as refresh:
            result = quiet_main(
                mc_audit.main,
                [
                    str(self.campaign),
                    "--mode",
                    "recalc",
                    "--source-dir",
                    str(self.source),
                    "--output",
                    str(self.control),
                    "--refresh-checker-evidence",
                ],
            )
        self.assertEqual(result, 2)
        refresh.assert_not_called()
        self.assert_control_preserved()

    def test_mc_audit_rejects_source_destination(self) -> None:
        source_payload = self.source / "qqps_91.25_21000.sdst"
        source_payload.write_bytes(self.sentinel)
        result = quiet_main(
            mc_audit.main,
            [
                str(self.campaign),
                "--mode",
                "recalc",
                "--source-dir",
                str(self.source),
                "--output",
                str(source_payload),
            ],
        )
        self.assertEqual(result, 2)
        self.assertEqual(source_payload.read_bytes(), self.sentinel)

    def test_lepton_summary_rejects_campaign_input_destination(self) -> None:
        result = quiet_main(
            lepton_summary.main,
            [str(self.campaign), "--output", str(self.control)],
        )
        self.assertEqual(result, 2)
        self.assert_control_preserved()

    def test_compare_rejects_raw_alias_before_discovery_failure(self) -> None:
        left = self.root / "left.root"
        left.write_bytes(self.sentinel)
        missing_right = self.root / "missing-right.root"
        result = quiet_main(
            comparison.main,
            [str(left), str(missing_right), "--output", str(left)],
        )
        self.assertEqual(result, 2)
        self.assertEqual(left.read_bytes(), self.sentinel)

    def test_compare_rejects_hardlink_and_in_tree_destinations(self) -> None:
        left = self.root / "left.root"
        right = self.root / "right.root"
        left.write_bytes(self.sentinel)
        right.write_bytes(b"RIGHT\n")
        hardlink = self.root / "left-report.json"
        os.link(left, hardlink)
        result = quiet_main(
            comparison.main,
            [str(left), str(right), "--output", str(hardlink)],
        )
        self.assertEqual(result, 2)
        self.assertEqual(left.read_bytes(), self.sentinel)
        self.assertEqual(hardlink.read_bytes(), self.sentinel)

        left_dir = self.root / "left-dir"
        right_dir = self.root / "right-dir"
        left_dir.mkdir()
        right_dir.mkdir()
        in_tree = left_dir / "comparison.json"
        result = quiet_main(
            comparison.main,
            [str(left_dir), str(right_dir), "--output", str(in_tree)],
        )
        self.assertEqual(result, 2)
        self.assertFalse(in_tree.exists())


if __name__ == "__main__":
    unittest.main()
