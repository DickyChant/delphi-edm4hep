#!/usr/bin/env python3
"""Focused tests for lepton-pair selection and mass hypotheses."""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("plot_lepton_pid_validation.py")
SPEC = importlib.util.spec_from_file_location("plot_lepton_pid_validation", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class LeptonMassContractTest(unittest.TestCase):
    @staticmethod
    def particle(px: float, py: float, pz: float, charge: float) -> object:
        momentum = math.sqrt(px * px + py * py + pz * pz)
        return MODULE.ParticleInfo(charge, momentum, px, py, pz)

    def test_back_to_back_tracks_use_explicit_muon_mass_hypothesis(self) -> None:
        momentum = 45.625
        first = self.particle(momentum, 0.0, 0.0, -1.0)
        second = self.particle(-momentum, 0.0, 0.0, 1.0)
        observed = MODULE.two_body_invariant_mass(
            first, second, MODULE.MUON_MASS_GEV
        )
        expected = 2.0 * math.hypot(momentum, MODULE.MUON_MASS_GEV)
        self.assertAlmostEqual(observed, expected, places=12)

    def test_electron_and_muon_hypotheses_are_distinct(self) -> None:
        first = self.particle(20.0, 2.0, 1.0, -1.0)
        second = self.particle(-19.0, -2.0, -1.0, 1.0)
        electron_mass = MODULE.two_body_invariant_mass(
            first, second, MODULE.ELECTRON_MASS_GEV
        )
        muon_mass = MODULE.two_body_invariant_mass(
            first, second, MODULE.MUON_MASS_GEV
        )
        self.assertGreater(muon_mass, electron_mass)

    def test_negative_mass_hypothesis_is_rejected(self) -> None:
        first = self.particle(20.0, 0.0, 0.0, -1.0)
        second = self.particle(-20.0, 0.0, 0.0, 1.0)
        with self.assertRaises(MODULE.ValidationError):
            MODULE.two_body_invariant_mass(first, second, -1.0)

    def test_documented_muid_bits_are_applied_independently(self) -> None:
        standard = MODULE.lepton_pair_decisions(0x4, 0x4, (0, -1), (0, -1))
        self.assertTrue(standard["muon_standard_double_tag"])
        self.assertFalse(standard["muon_tight_double_tag"])
        tight = MODULE.lepton_pair_decisions(0x8, 0x8, (0, -1), (0, -1))
        self.assertFalse(tight["muon_standard_double_tag"])
        self.assertTrue(tight["muon_tight_double_tag"])

    def test_elid_standard_and_tight_require_conversion_veto(self) -> None:
        accepted = MODULE.lepton_pair_decisions(0, 0, (4, 0), (5, 0))
        self.assertTrue(
            accepted["electron_standard_conversion_veto_double_tag"]
        )
        self.assertFalse(accepted["electron_tight_conversion_veto_double_tag"])
        tight = MODULE.lepton_pair_decisions(0, 0, (5, 0), (5, 0))
        self.assertTrue(tight["electron_tight_conversion_veto_double_tag"])
        conversion = MODULE.lepton_pair_decisions(0, 0, (5, 0), (5, 1))
        self.assertFalse(
            conversion["electron_standard_conversion_veto_double_tag"]
        )
        self.assertFalse(conversion["electron_tight_conversion_veto_double_tag"])


if __name__ == "__main__":
    unittest.main()
