#!/usr/bin/env python3
"""Produce fail-closed DELPHI 94c lepton/PID validation plots.

The input is the recalculated-only ``lolept94_c2`` campaign produced by
``batch_leptonic_long_94c.sh``.  A tape is accepted only when its final ROOT
file, completion marker, and frozen per-tape ``audit_lepton_pid.py`` report are
mutually consistent.  This program then independently follows every exact
ParticleID relation, recreates the complete audit counter set, and requires an
exact match before publishing any plots.

The target-response panels reproduce the data-side definitions on pages 9--11
of ``slides/target.pdf``.  MUID, ELID, high-momentum opposite-sign-pair, and
explicit-mass-hypothesis dimuon/dielectron panels are population diagnostics,
not efficiency or background-corrected measurements.

Examples (run inside the pinned Key4hep environment)::

  plot_lepton_pid_validation.py CAMPAIGN --tape Y13718.1 -o OUTPUT
  plot_lepton_pid_validation.py CAMPAIGN --all -o OUTPUT

``--all`` is deliberately explicit: there is no implicit full-campaign mode.
The output directory must not already exist and must be outside CAMPAIGN, so a
failure cannot alter live production products or leave a partial publication.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import shlex
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


REPORT_FORMAT = "delphi-lolept94-c2-lepton-pid-validation-v1"
COMPLETE_FORMAT = "delphi-lolept94-c2-lepton-pid-validation-complete-v1"
DATASET = "lolept94_c2"
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
HIGH_P_GEV = 20.0
# PDG lepton masses in GeV/c^2.  The stored sDST particle momentum is used as
# the measured three-vector; the energy is deliberately recomputed for each
# channel under the corresponding mass hypothesis instead of trusting a
# generic ReconstructedParticle energy assignment.
ELECTRON_MASS_GEV = 0.000_510_998_95
MUON_MASS_GEV = 0.105_658_375_5
MASS_MIN_GEV = 0.0
MASS_MAX_GEV = 130.0
MASS_BINS = 260
PARTICLE_COLLECTION = "sDST_MAIN_Particles"
PID_SPECS: Mapping[str, Tuple[int, int]] = {
    "sDST_MUID_MuonID": (2, 3),
    "sDST_ELID_ElectronID": (3, 2),
    "sDST_HAID_dEdx": (1, 2),
    "sDST_HAID_HadronID": (4, 18),
}
REQUIRED_COLLECTIONS = (PARTICLE_COLLECTION, *PID_SPECS.keys())
MUID_BITS: Tuple[Tuple[str, int], ...] = (
    ("very_loose", 0),
    ("loose", 1),
    ("standard", 2),
    ("tight", 3),
    ("hcal", 4),
)
MUID_KNOWN_MASK = sum(1 << bit for _, bit in MUID_BITS)
PAIR_CATEGORIES = (
    "all_charged",
    "muon_standard_tag_probe",
    "muon_standard_double_tag",
    "muon_tight_tag_probe",
    "muon_tight_double_tag",
    "electron_standard_tag_probe",
    "electron_standard_double_tag",
    "electron_standard_conversion_veto_tag_probe",
    "electron_standard_conversion_veto_double_tag",
    "electron_tight_conversion_veto_tag_probe",
    "electron_tight_conversion_veto_double_tag",
)
PAIR_LABELS = (
    "all OS",
    "#mu std #geq1",
    "#mu std both",
    "#mu tight #geq1",
    "#mu tight both",
    "e std #geq1",
    "e std both",
    "e std+CV #geq1",
    "e std+CV both",
    "e tight+CV #geq1",
    "e tight+CV both",
)
DEDX_COUNTERS = (
    "valid_rows",
    "positive",
    "nonpositive",
    "sigma_nonnegative",
    "sigma_negative",
    "target_plot_eligible",
)
RICH_COUNTERS = (
    "valid_rows",
    "theta_positive",
    "n_photoelectrons_ge_3",
    "flag_nonzero",
    "quality_flag_pass",
    "theta_positive_and_n_photoelectrons_ge_3",
    "target_plot_eligible",
)
TARGET_SELECTIONS = {
    "dedx": "parameters[0] > 0 and linked particle momentum > 0",
    "rich_gas": (
        "parameters[8] > 0, parameters[10] >= 3, "
        "all low four quality bits of parameters[12] set, and linked particle momentum > 0"
    ),
    "rich_liquid": (
        "parameters[13] > 0, parameters[15] >= 3, "
        "parameters[17] != 0, and linked particle momentum > 0"
    ),
}


class ValidationError(RuntimeError):
    """A provenance, schema, relation, or counter contract was violated."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def write_text_atomic(path: Path, payload: str) -> None:
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def require_regular(path: Path, context: str) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
        raise ValidationError(f"{context}: required nonempty regular file is missing: {path}")


def load_key_values(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        if "=" not in raw:
            raise ValidationError(f"{path}:{line_number}: expected key=value")
        key, value = raw.split("=", 1)
        if not key or key in values:
            raise ValidationError(f"{path}:{line_number}: empty or duplicate key {key!r}")
        values[key] = value
    return values


def parse_validation_summary(value: str, source: str, context: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    try:
        tokens = shlex.split(value)
    except ValueError as exc:
        raise ValidationError(f"{context}: malformed validation summary: {exc}") from exc
    for token in tokens:
        if "=" not in token:
            raise ValidationError(f"{context}: malformed validation token {token!r}")
        key, item = token.split("=", 1)
        if not key or key in parsed:
            raise ValidationError(f"{context}: empty or duplicate validation key {key!r}")
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
        "identity_failures": "0",
        "mode_failures": "0",
        "recalculated_failures": "0",
        "missing_collections": "0",
        "validity_contract_failures": "0",
    }
    for key, wanted in expected.items():
        if parsed.get(key) != wanted:
            raise ValidationError(
                f"{context}: validation {key}={parsed.get(key)!r}, expected {wanted!r}"
            )
    return parsed


def parse_frozen_v1_validation_summary(value: str, context: str) -> Dict[str, str]:
    """Parse only the checker schema bound to the exact frozen v1 campaign."""
    parsed: Dict[str, str] = {}
    try:
        tokens = shlex.split(value)
    except ValueError as exc:
        raise ValidationError(f"{context}: malformed frozen validation summary: {exc}") from exc
    for token in tokens:
        key, separator, item = token.partition("=")
        if not separator or not key or key in parsed:
            raise ValidationError(f"{context}: malformed frozen validation token {token!r}")
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
            raise ValidationError(
                f"{context}: frozen validation {key}={parsed.get(key)!r}, "
                f"expected {wanted!r}"
            )
    return parsed


def integer(value: Any, context: str, *, positive: bool = False) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{context}: boolean is not an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{context}: invalid integer {value!r}") from exc
    if str(result) != str(value):
        raise ValidationError(f"{context}: noncanonical integer {value!r}")
    if result < 0 or (positive and result == 0):
        qualifier = "positive" if positive else "nonnegative"
        raise ValidationError(f"{context}: expected {qualifier} integer, got {result}")
    return result


def object_key(obj: Any) -> Tuple[int, int]:
    oid = obj.getObjectID()
    return int(oid.collectionID), int(oid.index)


def sorted_counter(counter: Counter[Any]) -> Dict[str, int]:
    def order(item: Tuple[Any, int]) -> Tuple[int, Any]:
        key = item[0]
        return (0, key) if isinstance(key, int) else (1, str(key))

    return {str(key): int(value) for key, value in sorted(counter.items(), key=order)}


def first_difference(expected: Any, actual: Any, path: str = "summary") -> Optional[str]:
    if type(expected) is not type(actual):
        return f"{path}: type {type(actual).__name__}, expected {type(expected).__name__}"
    if isinstance(expected, Mapping):
        expected_keys = set(expected)
        actual_keys = set(actual)
        if expected_keys != actual_keys:
            return (
                f"{path}: keys differ; missing={sorted(expected_keys - actual_keys)} "
                f"extra={sorted(actual_keys - expected_keys)}"
            )
        for key in sorted(expected):
            difference = first_difference(expected[key], actual[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}: length {len(actual)}, expected {len(expected)}"
        for index, (wanted, found) in enumerate(zip(expected, actual)):
            difference = first_difference(wanted, found, f"{path}[{index}]")
            if difference:
                return difference
        return None
    if expected != actual:
        return f"{path}: {actual!r}, expected {expected!r}"
    return None


@dataclass(frozen=True)
class ParticleInfo:
    charge: float
    momentum: float
    px: float
    py: float
    pz: float


def two_body_invariant_mass(
    particle_a: ParticleInfo,
    particle_b: ParticleInfo,
    mass_hypothesis_gev: float,
) -> float:
    """Return m(a,b) after assigning the same explicit mass to both tracks."""
    if not math.isfinite(mass_hypothesis_gev) or mass_hypothesis_gev < 0.0:
        raise ValidationError(f"invalid mass hypothesis {mass_hypothesis_gev!r}")
    energy_a = math.hypot(particle_a.momentum, mass_hypothesis_gev)
    energy_b = math.hypot(particle_b.momentum, mass_hypothesis_gev)
    total_energy = energy_a + energy_b
    total_px = particle_a.px + particle_b.px
    total_py = particle_a.py + particle_b.py
    total_pz = particle_a.pz + particle_b.pz
    mass_squared = (
        total_energy * total_energy
        - total_px * total_px
        - total_py * total_py
        - total_pz * total_pz
    )
    # A tiny negative value is possible from floating-point cancellation.  A
    # material spacelike result is a broken kinematic contract and must not be
    # silently folded into the first histogram bin.
    scale = max(total_energy * total_energy, 1.0)
    if mass_squared < -1.0e-10 * scale:
        raise ValidationError(
            f"materially negative pair mass squared {mass_squared!r} GeV^2"
        )
    return math.sqrt(max(mass_squared, 0.0))


def lepton_pair_decisions(
    muon_tag_a: int,
    muon_tag_b: int,
    electron_tag_a: Tuple[int, int],
    electron_tag_b: Tuple[int, int],
) -> Dict[str, bool]:
    """Apply the documented MUID/ELID working points to one charged pair."""
    mu_standard_a, mu_standard_b = bool(muon_tag_a & 0x4), bool(muon_tag_b & 0x4)
    mu_tight_a, mu_tight_b = bool(muon_tag_a & 0x8), bool(muon_tag_b & 0x8)
    el_standard_a = electron_tag_a[0] in (4, 5)
    el_standard_b = electron_tag_b[0] in (4, 5)
    el_standard_veto_a = el_standard_a and electron_tag_a[1] == 0
    el_standard_veto_b = el_standard_b and electron_tag_b[1] == 0
    el_tight_veto_a = electron_tag_a[0] == 5 and electron_tag_a[1] == 0
    el_tight_veto_b = electron_tag_b[0] == 5 and electron_tag_b[1] == 0
    return {
        "all_charged": True,
        "muon_standard_tag_probe": mu_standard_a or mu_standard_b,
        "muon_standard_double_tag": mu_standard_a and mu_standard_b,
        "muon_tight_tag_probe": mu_tight_a or mu_tight_b,
        "muon_tight_double_tag": mu_tight_a and mu_tight_b,
        "electron_standard_tag_probe": el_standard_a or el_standard_b,
        "electron_standard_double_tag": el_standard_a and el_standard_b,
        "electron_standard_conversion_veto_tag_probe": (
            el_standard_veto_a or el_standard_veto_b
        ),
        "electron_standard_conversion_veto_double_tag": (
            el_standard_veto_a and el_standard_veto_b
        ),
        "electron_tight_conversion_veto_tag_probe": (
            el_tight_veto_a or el_tight_veto_b
        ),
        "electron_tight_conversion_veto_double_tag": (
            el_tight_veto_a and el_tight_veto_b
        ),
    }


@dataclass(frozen=True)
class TapeInput:
    number: int
    tape: str
    input_size: int
    root: Path
    marker: Path
    audit: Path
    events: int
    expected_summary: Mapping[str, Any]
    marker_sha256: str
    audit_sha256: str
    root_size: int
    root_inode: int
    root_mtime_ns: int


@dataclass
class Metrics:
    events: int = 0
    particles: int = 0
    collection_rows: Counter[str] = field(default_factory=Counter)
    parameter_vectors_checked: int = 0
    relations_checked: int = 0
    relations_valid: int = 0
    muon_raw_tags: Counter[int] = field(default_factory=Counter)
    muon_bit_counts: Counter[str] = field(default_factory=Counter)
    electron_tags: Counter[int] = field(default_factory=Counter)
    electron_conversion_tags: Counter[int] = field(default_factory=Counter)
    electron_tag_by_conversion: Counter[str] = field(default_factory=Counter)
    electron_conversion_veto_rows: int = 0
    electron_standard_rows: int = 0
    electron_standard_conversion_veto_rows: int = 0
    electron_undocumented_tag_rows: int = 0
    electron_undocumented_conversion_rows: int = 0
    dedx: Counter[str] = field(default_factory=Counter)
    rich_gas: Counter[str] = field(default_factory=Counter)
    rich_liquid: Counter[str] = field(default_factory=Counter)
    rich_gas_flags: Counter[int] = field(default_factory=Counter)
    rich_liquid_flags: Counter[int] = field(default_factory=Counter)
    pair_counts: Counter[str] = field(default_factory=Counter)
    pair_events: Counter[str] = field(default_factory=Counter)

    def merge(self, other: "Metrics") -> None:
        for scalar in (
            "events",
            "particles",
            "parameter_vectors_checked",
            "relations_checked",
            "relations_valid",
            "electron_conversion_veto_rows",
            "electron_standard_rows",
            "electron_standard_conversion_veto_rows",
            "electron_undocumented_tag_rows",
            "electron_undocumented_conversion_rows",
        ):
            setattr(self, scalar, getattr(self, scalar) + getattr(other, scalar))
        for counter in (
            "collection_rows",
            "muon_raw_tags",
            "muon_bit_counts",
            "electron_tags",
            "electron_conversion_tags",
            "electron_tag_by_conversion",
            "dedx",
            "rich_gas",
            "rich_liquid",
            "rich_gas_flags",
            "rich_liquid_flags",
            "pair_counts",
            "pair_events",
        ):
            getattr(self, counter).update(getattr(other, counter))

    def as_audit_json(self) -> Dict[str, Any]:
        return {
            "events": self.events,
            "particles": self.particles,
            "collection_rows": {
                name: int(self.collection_rows[name]) for name in REQUIRED_COLLECTIONS
            },
            "particle_id_contract": {
                "parameter_vectors_checked": self.parameter_vectors_checked,
                "relations_checked": self.relations_checked,
                "relations_valid": self.relations_valid,
            },
            "muon_id": {
                "raw_tag_distribution": sorted_counter(self.muon_raw_tags),
                "set_bit_counts": {
                    name: int(self.muon_bit_counts[name]) for name, _ in MUID_BITS
                },
            },
            "electron_id": {
                "tag_distribution": sorted_counter(self.electron_tags),
                "conversion_tag_distribution": sorted_counter(
                    self.electron_conversion_tags
                ),
                "tag_by_conversion_distribution": sorted_counter(
                    self.electron_tag_by_conversion
                ),
                "conversion_veto_rows": self.electron_conversion_veto_rows,
                "standard_or_tighter_rows": self.electron_standard_rows,
                "standard_or_tighter_conversion_veto_rows": (
                    self.electron_standard_conversion_veto_rows
                ),
                "undocumented_tag_outside_1_to_5_rows": (
                    self.electron_undocumented_tag_rows
                ),
                "undocumented_conversion_tag_outside_0_to_3_rows": (
                    self.electron_undocumented_conversion_rows
                ),
            },
            "target_response": {
                "dedx": {name: int(self.dedx[name]) for name in DEDX_COUNTERS},
                "rich_gas": {
                    **{name: int(self.rich_gas[name]) for name in RICH_COUNTERS},
                    "flag_distribution": sorted_counter(self.rich_gas_flags),
                },
                "rich_liquid": {
                    **{name: int(self.rich_liquid[name]) for name in RICH_COUNTERS},
                    "flag_distribution": sorted_counter(self.rich_liquid_flags),
                },
            },
            "opposite_sign_high_momentum_diagnostics": {
                "minimum_momentum_gev_per_particle": HIGH_P_GEV,
                "categories": {
                    name: {
                        "pairs": int(self.pair_counts[name]),
                        "events_with_at_least_one_pair": int(self.pair_events[name]),
                    }
                    for name in PAIR_CATEGORIES
                },
            },
        }


class Histograms:
    def __init__(self, root: Any) -> None:
        root.TH1.AddDirectory(False)
        self.dedx = root.TH2D(
            "dedx_vs_log10p", ";log_{10}(p/GeV);dE/dx (norm.)", 135, -1.0, 1.7, 125, 0.0, 2.5
        )
        self.rich_liquid = root.TH2D(
            "rich_liquid_theta_vs_log10p",
            ";log_{10}(p/GeV);#theta_{C} liquid (rad)",
            135,
            -1.0,
            1.7,
            150,
            0.0,
            0.75,
        )
        self.rich_gas = root.TH2D(
            "rich_gas_theta_vs_log10p",
            ";log_{10}(p/GeV);#theta_{C} gas (rad)",
            135,
            -1.0,
            1.7,
            160,
            0.0,
            0.08,
        )
        self.muid_raw = root.TH1D("muid_raw_tag", ";raw MUID bit mask;rows", 31, 0.5, 31.5)
        self.muid_bits = root.TH1D("muid_set_bits", ";MUID working-point bit;rows with bit set", 5, 0.5, 5.5)
        for index, (name, _) in enumerate(MUID_BITS, 1):
            self.muid_bits.GetXaxis().SetBinLabel(index, name.replace("_", " "))
        self.elid_tag = root.TH1D("elid_tag", ";ELID tag;rows", 9, 0.5, 9.5)
        self.elid_conversion = root.TH1D(
            "elid_conversion_tag", ";ELID conversion tag;rows", 10, -0.5, 9.5
        )
        self.elid_tag_conversion = root.TH2D(
            "elid_tag_vs_conversion", ";ELID tag;conversion tag", 9, 0.5, 9.5, 10, -0.5, 9.5
        )
        self.pair_counts = root.TH1D(
            "high_p_os_pair_counts", ";category;opposite-sign pairs", len(PAIR_CATEGORIES), 0.5, len(PAIR_CATEGORIES) + 0.5
        )
        self.pair_events = root.TH1D(
            "high_p_os_event_counts", ";category;events with #geq1 pair", len(PAIR_CATEGORIES), 0.5, len(PAIR_CATEGORIES) + 0.5
        )
        mass_axis = f";m_{{ll}} (GeV/c^{{2}});opposite-sign candidate pairs / {(MASS_MAX_GEV - MASS_MIN_GEV) / MASS_BINS:g} GeV"
        self.dimuon_standard_mass = root.TH1D(
            "dimuon_standard_mass",
            mass_axis,
            MASS_BINS,
            MASS_MIN_GEV,
            MASS_MAX_GEV,
        )
        self.dimuon_tight_mass = root.TH1D(
            "dimuon_tight_mass",
            mass_axis,
            MASS_BINS,
            MASS_MIN_GEV,
            MASS_MAX_GEV,
        )
        self.dielectron_standard_conversion_veto_mass = root.TH1D(
            "dielectron_standard_conversion_veto_mass",
            mass_axis,
            MASS_BINS,
            MASS_MIN_GEV,
            MASS_MAX_GEV,
        )
        self.dielectron_tight_conversion_veto_mass = root.TH1D(
            "dielectron_tight_conversion_veto_mass",
            mass_axis,
            MASS_BINS,
            MASS_MIN_GEV,
            MASS_MAX_GEV,
        )
        for index, label in enumerate(PAIR_LABELS, 1):
            self.pair_counts.GetXaxis().SetBinLabel(index, label)
            self.pair_events.GetXaxis().SetBinLabel(index, label)

    @property
    def all(self) -> Tuple[Any, ...]:
        return (
            self.dedx,
            self.rich_liquid,
            self.rich_gas,
            self.muid_raw,
            self.muid_bits,
            self.elid_tag,
            self.elid_conversion,
            self.elid_tag_conversion,
            self.pair_counts,
            self.pair_events,
            self.dimuon_standard_mass,
            self.dimuon_tight_mass,
            self.dielectron_standard_conversion_veto_mass,
            self.dielectron_tight_conversion_veto_mass,
        )


def parse_manifest(path: Path) -> Dict[int, int]:
    require_regular(path, "campaign manifest")
    if sha256(path) != EXPECTED_MANIFEST_SHA256:
        raise ValidationError("campaign manifest SHA-256 differs from the audited official inventory")
    rows: Dict[int, int] = {}
    total = 0
    for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = raw.split("\t")
        expected_name = f"Y13718.{index}.al"
        if len(fields) != 2 or fields[0] != expected_name:
            raise ValidationError(f"{path}:{index}: expected exact row for {expected_name}")
        size = integer(fields[1], f"{path}:{index}", positive=True)
        rows[index] = size
        total += size
    if len(rows) != EXPECTED_FILES or total != EXPECTED_INPUT_BYTES:
        raise ValidationError(
            f"official inventory mismatch: files={len(rows)} bytes={total}"
        )
    return rows


def normalize_tape(token: str) -> int:
    value = token
    if value.startswith("Y13718."):
        value = value[len("Y13718.") :]
    if value.endswith(".al"):
        value = value[:-3]
    if not value.isdigit() or str(int(value)) != value:
        raise ValidationError(f"invalid tape selector {token!r}; use N or Y13718.N")
    number = int(value)
    if number < 1 or number > EXPECTED_FILES:
        raise ValidationError(f"tape number outside 1..{EXPECTED_FILES}: {number}")
    return number


def audited_input_name_ok(audited_input: Path, root: Path, tape: str) -> bool:
    if audited_input.resolve() == root.resolve():
        return True
    prefix = f".lolept94_c2_{tape}."
    return (
        audited_input.parent.resolve() == root.parent.resolve()
        and audited_input.name.startswith(prefix)
        and audited_input.name.endswith(".tmp.root")
        and len(audited_input.name) == len(prefix) + 6 + len(".tmp.root")
    )


def validate_tape(
    campaign: Path,
    config: Mapping[str, str],
    config_sha: str,
    number: int,
    input_size: int,
) -> TapeInput:
    tape = f"Y13718.{number}"
    root = campaign / "edm4hep" / f"lolept94_c2_{tape}.edm4hep.root"
    marker = Path(f"{root}.complete")
    audit = campaign / "audits" / f"{tape}.lepton_pid.json"
    frozen_v1 = config.get("_input_contract") == "exact-frozen-v1-campaign-sha256"
    require_regular(root, tape)
    require_regular(marker, tape)
    require_regular(audit, tape)
    root_stat = root.stat()
    marker_values = load_key_values(marker)
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
        "output_size_bytes": str(root_stat.st_size),
        "btag_mode": "recalc",
        "recalculated": "1",
        "identity_check": "exact-ordered-run-event-fileSeq",
        "campaign_sha256": config_sha,
        "auditor_sha256": config["auditor_sha256"],
        "checker_sha256": config["checker_sha256"],
        "lepton_schema_audit_sha256": sha256(audit),
    }
    if not frozen_v1:
        expected_marker["output_sha256"] = root_sha
    for key, wanted in expected_marker.items():
        if marker_values.get(key) != wanted:
            raise ValidationError(
                f"{marker}: {key}={marker_values.get(key)!r}, expected {wanted!r}"
            )
    events = integer(marker_values.get("events"), f"{marker}:events", positive=True)
    if frozen_v1:
        validation = parse_frozen_v1_validation_summary(
            marker_values.get("validation", ""), f"{marker}:validation"
        )
        if integer(
            validation.get("entries"), f"{marker}:validation.entries", positive=True
        ) != events:
            raise ValidationError(
                f"{marker}: frozen checker entry count differs from marker"
            )
    else:
        for source, key in (("sDST", "sdst_validation"), ("fDST", "fdst_validation")):
            validation = parse_validation_summary(
                marker_values.get(key, ""), source, f"{marker}:{key}"
            )
            if integer(
                validation.get("entries"), f"{marker}:{key}.entries", positive=True
            ) != events:
                raise ValidationError(
                    f"{marker}: {source} checker entry count differs from marker"
                )

    try:
        report = json.loads(audit.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot decode {audit}: {exc}") from exc
    if report.get("format") != "delphi-edm4hep-lepton-pid-audit-v1":
        raise ValidationError(f"{audit}: unexpected report format")
    if report.get("status") != "PASS" or report.get("failures", {}).get("count") != 0:
        raise ValidationError(f"{audit}: audit is not PASS with zero failures")
    configuration = report.get("configuration")
    if not isinstance(configuration, Mapping):
        raise ValidationError(f"{audit}: missing configuration")
    if configuration.get("target_response_selections") != TARGET_SELECTIONS:
        raise ValidationError(f"{audit}: target-response selections differ from the frozen contract")
    pair_config = configuration.get("opposite_sign_high_momentum_diagnostics")
    if not isinstance(pair_config, Mapping) or pair_config.get(
        "minimum_momentum_gev_per_particle"
    ) != HIGH_P_GEV:
        raise ValidationError(f"{audit}: high-momentum pair threshold is not {HIGH_P_GEV}")
    inputs = report.get("inputs")
    if not isinstance(inputs, Mapping) or inputs.get("file_count") != 1:
        raise ValidationError(f"{audit}: expected exactly one audited input")
    if inputs.get("total_size_bytes") != root_stat.st_size:
        raise ValidationError(f"{audit}: audited byte count differs from ROOT file")
    input_files = inputs.get("files")
    if not isinstance(input_files, list) or len(input_files) != 1:
        raise ValidationError(f"{audit}: malformed audited input list")
    audited_input = Path(input_files[0])
    if not audited_input_name_ok(audited_input, root, tape):
        raise ValidationError(f"{audit}: audited input is not the atomic source of {root}")
    file_reports = report.get("files")
    if not isinstance(file_reports, list) or len(file_reports) != 1:
        raise ValidationError(f"{audit}: expected one file report")
    file_report = file_reports[0]
    if not isinstance(file_report, Mapping) or file_report.get("status") != "PASS":
        raise ValidationError(f"{audit}: file report is not PASS")
    if file_report.get("size_bytes") != root_stat.st_size:
        raise ValidationError(f"{audit}: file-report byte count differs from ROOT file")
    if file_report.get("path") != input_files[0]:
        raise ValidationError(f"{audit}: file-report path differs from audited input")
    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        raise ValidationError(f"{audit}: missing summary")
    if file_report.get("metrics") != summary:
        raise ValidationError(f"{audit}: single-file metrics differ from summary")
    if integer(summary.get("events"), f"{audit}:summary.events") != events:
        raise ValidationError(f"{audit}: event count differs from marker")
    contract = summary.get("particle_id_contract", {})
    if contract.get("relations_checked") != contract.get("relations_valid"):
        raise ValidationError(f"{audit}: ParticleID relations were not all valid")
    return TapeInput(
        number=number,
        tape=tape,
        input_size=input_size,
        root=root,
        marker=marker,
        audit=audit,
        events=events,
        expected_summary=summary,
        marker_sha256=sha256(marker),
        audit_sha256=sha256(audit),
        root_size=root_stat.st_size,
        root_inode=root_stat.st_ino,
        root_mtime_ns=root_stat.st_mtime_ns,
    )


def validate_campaign(
    campaign: Path, requested_tapes: Sequence[str], all_tapes: bool
) -> Tuple[Path, Mapping[str, str], str, str, List[TapeInput]]:
    try:
        campaign = campaign.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValidationError(f"campaign does not exist: {campaign}") from exc
    if not campaign.is_dir():
        raise ValidationError(f"campaign is not a directory: {campaign}")
    config_path = campaign / "campaign.conf"
    manifest_path = campaign / "inputs.manifest.tsv"
    require_regular(config_path, "campaign configuration")
    config = load_key_values(config_path)
    config_sha = sha256(config_path)
    frozen_v1 = config_sha == FROZEN_V1_CAMPAIGN_SHA256
    expected_config = {
        "format": (
            "delphi-lolept94-c2-recalc-v1"
            if frozen_v1
            else "delphi-lolept94-c2-recalc-v2"
        ),
        "dataset": DATASET,
        "btag_mode": "recalc",
        "recalculated": "1",
        "file_count": str(EXPECTED_FILES),
        "input_bytes": str(EXPECTED_INPUT_BYTES),
        "expected_events": str(CATALOG_EVENTS if frozen_v1 else EXPECTED_EVENTS),
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "key4hep_release": "2026-04-08",
    }
    if not frozen_v1:
        expected_config.update(
            {
                "catalog_events": str(CATALOG_EVENTS),
                "catalog_event_discrepancy": str(CATALOG_EVENT_DISCREPANCY),
            }
        )
    for key, wanted in expected_config.items():
        if config.get(key) != wanted:
            raise ValidationError(
                f"{config_path}: {key}={config.get(key)!r}, expected {wanted!r}"
            )
    for key in ("auditor_sha256", "checker_sha256"):
        value = config.get(key, "")
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValidationError(f"{config_path}: invalid {key}")
    config["_input_contract"] = (
        "exact-frozen-v1-campaign-sha256" if frozen_v1 else "current-v2"
    )
    manifest = parse_manifest(manifest_path)
    if all_tapes:
        numbers = list(range(1, EXPECTED_FILES + 1))
    else:
        numbers = [normalize_tape(token) for token in requested_tapes]
        if len(set(numbers)) != len(numbers):
            raise ValidationError("duplicate tape selector")
        numbers.sort()
    manifest_sha = sha256(manifest_path)
    tapes = [
        validate_tape(campaign, config, config_sha, number, manifest[number])
        for number in numbers
    ]
    return campaign, config, config_sha, manifest_sha, tapes


def integral_parameter(value: float, context: str) -> int:
    rounded = int(round(value))
    if abs(value - rounded) > 1.0e-5:
        raise ValidationError(f"{context}: expected integer-valued parameter, got {value!r}")
    return rounded


def relation_key(
    pid: Any,
    collection: str,
    particle_info: Mapping[Tuple[int, int], ParticleInfo],
    context: str,
    metrics: Metrics,
) -> Tuple[int, int]:
    metrics.relations_checked += 1
    try:
        particle = pid.getParticle()
        if not particle.isAvailable():
            raise ValueError("relation is unavailable")
        key = object_key(particle)
    except Exception as exc:
        raise ValidationError(f"{context}: {collection} relation cannot be resolved: {exc}") from exc
    if key not in particle_info:
        raise ValidationError(f"{context}: {collection} relation targets wrong ObjectID{key}")
    if particle_info[key].charge == 0.0:
        raise ValidationError(f"{context}: {collection} relation targets neutral ObjectID{key}")
    metrics.relations_valid += 1
    return key


def audit_rich_row(
    theta: float,
    n_photoelectrons: int,
    flag_value: int,
    momentum: float,
    counters: Counter[str],
    flag_distribution: Counter[int],
    required_flag_mask: Optional[int],
) -> bool:
    counters["valid_rows"] += 1
    flag_distribution[flag_value] += 1
    theta_ok = theta > 0.0
    photons_ok = n_photoelectrons >= 3
    flag_ok = (
        (flag_value & required_flag_mask) == required_flag_mask
        if required_flag_mask is not None
        else flag_value != 0
    )
    if theta_ok:
        counters["theta_positive"] += 1
    if photons_ok:
        counters["n_photoelectrons_ge_3"] += 1
    if flag_ok:
        counters["quality_flag_pass"] += 1
    if flag_value != 0:
        counters["flag_nonzero"] += 1
    if theta_ok and photons_ok:
        counters["theta_positive_and_n_photoelectrons_ge_3"] += 1
    eligible = theta_ok and photons_ok and flag_ok and momentum > 0.0
    if eligible:
        counters["target_plot_eligible"] += 1
    return eligible


def extract_frame(
    frame: Any,
    tape: str,
    event_index: int,
    metrics: Metrics,
    histograms: Histograms,
) -> None:
    context = f"{tape} event[{event_index}]"
    try:
        available = set(frame.getAvailableCollections())
    except Exception as exc:
        raise ValidationError(f"{context}: cannot read collection inventory: {exc}") from exc
    missing = [name for name in REQUIRED_COLLECTIONS if name not in available]
    if missing:
        raise ValidationError(f"{context}: missing required collections {missing}")

    particle_info: Dict[Tuple[int, int], ParticleInfo] = {}
    try:
        particles = list(frame.get(PARTICLE_COLLECTION))
    except Exception as exc:
        raise ValidationError(f"{context}: cannot read {PARTICLE_COLLECTION}: {exc}") from exc
    metrics.collection_rows[PARTICLE_COLLECTION] += len(particles)
    metrics.particles += len(particles)
    for row_index, particle in enumerate(particles):
        key = object_key(particle)
        if key in particle_info:
            raise ValidationError(f"{context}: duplicate particle ObjectID{key}")
        momentum = particle.getMomentum()
        px, py, pz = float(momentum.x), float(momentum.y), float(momentum.z)
        charge = float(particle.getCharge())
        if not all(math.isfinite(value) for value in (px, py, pz, charge)):
            raise ValidationError(f"{context}: nonfinite particle[{row_index}] kinematics")
        particle_info[key] = ParticleInfo(
            charge=charge,
            momentum=math.sqrt(px * px + py * py + pz * pz),
            px=px,
            py=py,
            pz=pz,
        )

    muon_tags: Dict[Tuple[int, int], int] = {}
    electron_tags: Dict[Tuple[int, int], Tuple[int, int]] = {}
    for collection_name, (expected_algorithm, expected_parameters) in PID_SPECS.items():
        try:
            rows = list(frame.get(collection_name))
        except Exception as exc:
            raise ValidationError(f"{context}: cannot read {collection_name}: {exc}") from exc
        metrics.collection_rows[collection_name] += len(rows)
        seen_relations: set[Tuple[int, int]] = set()
        for row_index, pid in enumerate(rows):
            row_context = f"{context} {collection_name}[{row_index}]"
            if int(pid.getAlgorithmType()) != expected_algorithm:
                raise ValidationError(f"{row_context}: wrong algorithmType")
            try:
                parameters = [float(value) for value in pid.getParameters()]
            except Exception as exc:
                raise ValidationError(f"{row_context}: cannot read parameters: {exc}") from exc
            metrics.parameter_vectors_checked += 1
            if len(parameters) != expected_parameters:
                raise ValidationError(
                    f"{row_context}: {len(parameters)} parameters, expected {expected_parameters}"
                )
            if not all(math.isfinite(value) for value in parameters):
                raise ValidationError(f"{row_context}: nonfinite parameter")
            key = relation_key(pid, collection_name, particle_info, row_context, metrics)
            if key in seen_relations:
                raise ValidationError(f"{row_context}: duplicate relation to ObjectID{key}")
            seen_relations.add(key)
            momentum = particle_info[key].momentum

            if collection_name == "sDST_MUID_MuonID":
                tag = integral_parameter(parameters[0], f"{row_context} parameter[0]")
                integral_parameter(parameters[2], f"{row_context} parameter[2]")
                metrics.muon_raw_tags[tag] += 1
                if tag <= 0 or tag & ~MUID_KNOWN_MASK:
                    raise ValidationError(f"{row_context}: invalid MUID bit mask {tag}")
                histograms.muid_raw.Fill(tag)
                for bit_index, (name, bit) in enumerate(MUID_BITS, 1):
                    if tag & (1 << bit):
                        metrics.muon_bit_counts[name] += 1
                        histograms.muid_bits.Fill(bit_index)
                muon_tags[key] = tag

            elif collection_name == "sDST_ELID_ElectronID":
                tag = integral_parameter(parameters[0], f"{row_context} parameter[0]")
                conversion = integral_parameter(parameters[1], f"{row_context} parameter[1]")
                metrics.electron_tags[tag] += 1
                metrics.electron_conversion_tags[conversion] += 1
                metrics.electron_tag_by_conversion[f"tag={tag},conversion={conversion}"] += 1
                if tag < 1 or tag > 9:
                    raise ValidationError(f"{row_context}: invalid ELID tag {tag}")
                if conversion < 0 or conversion > 9:
                    raise ValidationError(f"{row_context}: invalid conversion tag {conversion}")
                if tag not in range(1, 6):
                    metrics.electron_undocumented_tag_rows += 1
                if conversion not in range(0, 4):
                    metrics.electron_undocumented_conversion_rows += 1
                if conversion == 0:
                    metrics.electron_conversion_veto_rows += 1
                if tag in (4, 5):
                    metrics.electron_standard_rows += 1
                    if conversion == 0:
                        metrics.electron_standard_conversion_veto_rows += 1
                histograms.elid_tag.Fill(tag)
                histograms.elid_conversion.Fill(conversion)
                histograms.elid_tag_conversion.Fill(tag, conversion)
                electron_tags[key] = (tag, conversion)

            elif collection_name == "sDST_HAID_dEdx":
                dedx, sigma = parameters
                metrics.dedx["valid_rows"] += 1
                metrics.dedx["positive" if dedx > 0.0 else "nonpositive"] += 1
                metrics.dedx[
                    "sigma_nonnegative" if sigma >= 0.0 else "sigma_negative"
                ] += 1
                if momentum > 0.0 and dedx > 0.0:
                    metrics.dedx["target_plot_eligible"] += 1
                    histograms.dedx.Fill(math.log10(momentum), dedx)

            elif collection_name == "sDST_HAID_HadronID":
                gas_theta, gas_nph, gas_flag = parameters[8], parameters[10], parameters[12]
                liquid_theta, liquid_nph, liquid_flag = (
                    parameters[13],
                    parameters[15],
                    parameters[17],
                )
                gas_nph_int = integral_parameter(gas_nph, f"{row_context} parameter[10]")
                gas_flag_int = integral_parameter(gas_flag, f"{row_context} parameter[12]")
                liquid_nph_int = integral_parameter(liquid_nph, f"{row_context} parameter[15]")
                liquid_flag_int = integral_parameter(liquid_flag, f"{row_context} parameter[17]")
                if gas_nph_int < 0 or liquid_nph_int < 0:
                    raise ValidationError(f"{row_context}: negative RICH photoelectron count")
                if gas_flag_int < 0 or gas_flag_int & ~0x3F:
                    raise ValidationError(f"{row_context}: invalid gas RICH quality word {gas_flag_int}")
                if liquid_flag_int < 0 or liquid_flag_int & ~0x3F:
                    raise ValidationError(
                        f"{row_context}: invalid liquid RICH quality word {liquid_flag_int}"
                    )
                gas_eligible = audit_rich_row(
                    gas_theta,
                    gas_nph_int,
                    gas_flag_int,
                    momentum,
                    metrics.rich_gas,
                    metrics.rich_gas_flags,
                    0x0F,
                )
                liquid_eligible = audit_rich_row(
                    liquid_theta,
                    liquid_nph_int,
                    liquid_flag_int,
                    momentum,
                    metrics.rich_liquid,
                    metrics.rich_liquid_flags,
                    None,
                )
                if gas_eligible:
                    histograms.rich_gas.Fill(math.log10(momentum), gas_theta)
                if liquid_eligible:
                    histograms.rich_liquid.Fill(math.log10(momentum), liquid_theta)

    candidates = [
        (key, info)
        for key, info in particle_info.items()
        if info.momentum >= HIGH_P_GEV and info.charge != 0.0
    ]
    event_categories: set[str] = set()
    for first in range(len(candidates)):
        key_a, particle_a = candidates[first]
        for second in range(first + 1, len(candidates)):
            key_b, particle_b = candidates[second]
            if particle_a.charge * particle_b.charge >= 0.0:
                continue
            mu_a, mu_b = muon_tags.get(key_a, 0), muon_tags.get(key_b, 0)
            el_a, el_b = electron_tags.get(key_a, (0, -1)), electron_tags.get(key_b, (0, -1))
            decisions = lepton_pair_decisions(mu_a, mu_b, el_a, el_b)
            dimuon_mass: Optional[float] = None
            if decisions["muon_standard_double_tag"]:
                dimuon_mass = two_body_invariant_mass(
                    particle_a, particle_b, MUON_MASS_GEV
                )
                histograms.dimuon_standard_mass.Fill(dimuon_mass)
            if decisions["muon_tight_double_tag"]:
                if dimuon_mass is None:
                    dimuon_mass = two_body_invariant_mass(
                        particle_a, particle_b, MUON_MASS_GEV
                    )
                histograms.dimuon_tight_mass.Fill(dimuon_mass)
            if decisions["electron_standard_conversion_veto_double_tag"]:
                dielectron_mass = two_body_invariant_mass(
                    particle_a, particle_b, ELECTRON_MASS_GEV
                )
                histograms.dielectron_standard_conversion_veto_mass.Fill(
                    dielectron_mass
                )
                if decisions["electron_tight_conversion_veto_double_tag"]:
                    histograms.dielectron_tight_conversion_veto_mass.Fill(
                        dielectron_mass
                    )
            for category_index, name in enumerate(PAIR_CATEGORIES, 1):
                if decisions[name]:
                    metrics.pair_counts[name] += 1
                    event_categories.add(name)
                    histograms.pair_counts.Fill(category_index)
    for category_index, name in enumerate(PAIR_CATEGORIES, 1):
        if name in event_categories:
            metrics.pair_events[name] += 1
            histograms.pair_events.Fill(category_index)


def extract_tape(tape: TapeInput, root_io: Any, histograms: Histograms) -> Metrics:
    metrics = Metrics()
    try:
        frames = root_io.Reader(str(tape.root)).get("events")
        for event_index, frame in enumerate(frames):
            metrics.events += 1
            extract_frame(frame, tape.tape, event_index, metrics, histograms)
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(
            f"{tape.root}: ROOT/podio read failed: {type(exc).__name__}: {exc}"
        ) from exc
    if metrics.events == 0:
        raise ValidationError(f"{tape.root}: empty events frame category")
    difference = first_difference(tape.expected_summary, metrics.as_audit_json())
    if difference:
        raise ValidationError(f"{tape.tape}: independent counters differ from frozen audit: {difference}")
    current = tape.root.stat()
    if (
        current.st_size != tape.root_size
        or current.st_ino != tape.root_inode
        or current.st_mtime_ns != tape.root_mtime_ns
    ):
        raise ValidationError(f"{tape.root}: file changed while it was being read")
    return metrics


def in_range_entries(histogram: Any) -> int:
    return int(
        round(
            histogram.Integral(
                1,
                histogram.GetNbinsX(),
                1,
                histogram.GetNbinsY(),
            )
        )
    )


def one_dimensional_histogram_counts(histogram: Any) -> Dict[str, int]:
    bins = int(histogram.GetNbinsX())
    entries = int(round(histogram.GetEntries()))
    underflow = int(round(histogram.GetBinContent(0)))
    overflow = int(round(histogram.GetBinContent(bins + 1)))
    visible = int(round(histogram.Integral(1, bins)))
    if underflow + visible + overflow != entries:
        raise ValidationError(
            f"{histogram.GetName()}: histogram entries do not equal bin-content sum"
        )
    return {
        "pairs": entries,
        "visible_pairs": visible,
        "underflow_pairs": underflow,
        "overflow_pairs": overflow,
    }


def validate_mass_histograms(
    histograms: Histograms, summary: Mapping[str, Any]
) -> Dict[str, Any]:
    pair_summary = summary["opposite_sign_high_momentum_diagnostics"]["categories"]
    channels = {
        "dimuon_standard": (
            histograms.dimuon_standard_mass,
            "muon_standard_double_tag",
            MUON_MASS_GEV,
            "both MUID raw masks have bit 2 set (mask & 0x4 != 0)",
        ),
        "dimuon_tight": (
            histograms.dimuon_tight_mass,
            "muon_tight_double_tag",
            MUON_MASS_GEV,
            "both MUID raw masks have bit 3 set (mask & 0x8 != 0)",
        ),
        "dielectron_standard_conversion_veto": (
            histograms.dielectron_standard_conversion_veto_mass,
            "electron_standard_conversion_veto_double_tag",
            ELECTRON_MASS_GEV,
            "both ELID tags are in {4,5} and both conversion tags equal 0",
        ),
        "dielectron_tight_conversion_veto": (
            histograms.dielectron_tight_conversion_veto_mass,
            "electron_tight_conversion_veto_double_tag",
            ELECTRON_MASS_GEV,
            "both ELID tags equal 5 and both conversion tags equal 0",
        ),
    }
    result: Dict[str, Any] = {
        "minimum_momentum_gev_per_particle": HIGH_P_GEV,
        "opposite_sign_required": True,
        "momentum_source": f"{PARTICLE_COLLECTION}.momentum",
        "energy_definition": "sqrt(|p|^2 + assigned_lepton_mass^2) per particle",
        "histogram_range_gev": [MASS_MIN_GEV, MASS_MAX_GEV],
        "histogram_bins": MASS_BINS,
        "channels": {},
    }
    for name, (histogram, category, mass_hypothesis, selection) in channels.items():
        counts = one_dimensional_histogram_counts(histogram)
        expected = int(pair_summary[category]["pairs"])
        if counts["pairs"] != expected:
            raise ValidationError(
                f"{histogram.GetName()}: mass entries={counts['pairs']}, "
                f"but audited {category} pairs={expected}"
            )
        result["channels"][name] = {
            "selection": (
                f"opposite charge; both p >= {HIGH_P_GEV:g} GeV; {selection}"
            ),
            "mass_hypothesis_gev": mass_hypothesis,
            **counts,
        }
    return result


def draw_target_canvas(root: Any, histograms: Histograms, summary: Mapping[str, Any]) -> Tuple[Any, List[Any]]:
    canvas = root.TCanvas("target_response_canvas", "target response", 1900, 650)
    canvas.Divide(3, 1, 0.002, 0.002)
    owned: List[Any] = []
    panels = (
        (
            histograms.dedx,
            "DATA (94c) - TPC dE/dx vs p",
            "dE/dx>0; exact charged-particle relation",
            summary["target_response"]["dedx"]["target_plot_eligible"],
        ),
        (
            histograms.rich_liquid,
            "DATA (94c) - RICH liquid #theta_{C} vs p",
            "N_{pe}#geq3, #theta_{C}>0, FLAGL#neq0; exact relation",
            summary["target_response"]["rich_liquid"]["target_plot_eligible"],
        ),
        (
            histograms.rich_gas,
            "DATA (94c) - RICH gas #theta_{C} vs p",
            "N_{pe}#geq3, #theta_{C}>0, (FLAGG&0x0f)=0x0f; exact relation",
            summary["target_response"]["rich_gas"]["target_plot_eligible"],
        ),
    )
    for index, (histogram, title, selection, eligible) in enumerate(panels, 1):
        canvas.cd(index)
        root.gPad.SetLeftMargin(0.13)
        root.gPad.SetRightMargin(0.15)
        root.gPad.SetBottomMargin(0.12)
        root.gPad.SetTopMargin(0.12)
        root.gPad.SetLogz(True)
        histogram.SetTitle(title)
        histogram.SetMinimum(1.0)
        histogram.GetXaxis().SetTitleSize(0.045)
        histogram.GetYaxis().SetTitleSize(0.045)
        histogram.GetYaxis().SetTitleOffset(1.30)
        histogram.GetXaxis().SetLabelSize(0.038)
        histogram.GetYaxis().SetLabelSize(0.038)
        histogram.Draw("COLZ")
        note = root.TPaveText(0.13, 0.73, 0.80, 0.88, "NDC")
        note.SetFillColorAlpha(root.kWhite, 0.86)
        note.SetBorderSize(1)
        note.SetTextAlign(12)
        note.SetTextSize(0.029)
        note.AddText(selection)
        note.AddText(f"eligible={eligible:,}; visible={in_range_entries(histogram):,}")
        note.Draw()
        owned.append(note)
    canvas.Update()
    return canvas, owned


def draw_lepton_canvas(root: Any, histograms: Histograms) -> Tuple[Any, List[Any]]:
    canvas = root.TCanvas("lepton_id_diagnostics_canvas", "lepton ID diagnostics", 1600, 1100)
    canvas.Divide(2, 2, 0.002, 0.002)
    owned: List[Any] = []
    blue = root.TColor.GetColor("#3569a8")
    orange = root.TColor.GetColor("#d9782d")

    canvas.cd(1)
    root.gPad.SetLogy(True)
    root.gPad.SetBottomMargin(0.13)
    histograms.muid_raw.SetTitle("MUID raw bit-mask population - diagnostic, not efficiency")
    histograms.muid_raw.SetFillColor(blue)
    histograms.muid_raw.SetLineColor(blue)
    histograms.muid_raw.SetMinimum(0.8)
    histograms.muid_raw.Draw("HIST")

    canvas.cd(2)
    root.gPad.SetBottomMargin(0.18)
    muid_fraction = histograms.muid_bits.Clone("muid_set_bit_fraction_for_canvas")
    muid_fraction.SetDirectory(0)
    if histograms.muid_raw.GetEntries() > 0:
        muid_fraction.Scale(1.0 / histograms.muid_raw.GetEntries())
    muid_fraction.SetTitle("MUID bit-set fraction of MUID rows - diagnostic, not efficiency")
    muid_fraction.GetYaxis().SetTitle("fraction of MUID rows")
    muid_fraction.SetMaximum(1.05)
    muid_fraction.SetFillColor(blue)
    muid_fraction.SetLineColor(blue)
    muid_fraction.Draw("HIST TEXT0")
    owned.append(muid_fraction)

    canvas.cd(3)
    root.gPad.SetBottomMargin(0.13)
    elid_fraction = histograms.elid_tag.Clone("elid_tag_fraction_for_canvas")
    elid_fraction.SetDirectory(0)
    if histograms.elid_tag.GetEntries() > 0:
        elid_fraction.Scale(1.0 / histograms.elid_tag.GetEntries())
    elid_fraction.SetTitle("ELID tag population fraction - diagnostic, not efficiency")
    elid_fraction.GetYaxis().SetTitle("fraction of ELID rows")
    elid_fraction.SetFillColor(orange)
    elid_fraction.SetLineColor(orange)
    elid_fraction.Draw("HIST TEXT0")
    owned.append(elid_fraction)

    canvas.cd(4)
    root.gPad.SetRightMargin(0.15)
    root.gPad.SetLogz(True)
    histograms.elid_tag_conversion.SetTitle(
        "ELID tag vs conversion-tag population - diagnostic, not efficiency"
    )
    histograms.elid_tag_conversion.SetMinimum(1.0)
    histograms.elid_tag_conversion.Draw("COLZ")
    note = root.TPaveText(0.14, 0.75, 0.62, 0.88, "NDC")
    note.SetFillColorAlpha(root.kWhite, 0.86)
    note.SetBorderSize(1)
    note.SetTextAlign(12)
    note.SetTextSize(0.034)
    note.AddText("standard: tag in {4,5}")
    note.AddText("conversion veto: conversion tag = 0")
    note.Draw()
    owned.append(note)
    canvas.Update()
    return canvas, owned


def draw_pair_canvas(root: Any, histograms: Histograms) -> Tuple[Any, List[Any]]:
    canvas = root.TCanvas("high_p_os_pair_diagnostics_canvas", "OS pair diagnostics", 1800, 750)
    canvas.cd()
    root.gPad.SetBottomMargin(0.30)
    root.gPad.SetLeftMargin(0.09)
    root.gPad.SetRightMargin(0.03)
    pair_hist = histograms.pair_counts.Clone("high_p_os_pair_counts_for_canvas")
    event_hist = histograms.pair_events.Clone("high_p_os_event_counts_for_canvas")
    pair_hist.SetDirectory(0)
    event_hist.SetDirectory(0)
    pair_hist.SetTitle(
        "p#geq20 GeV opposite-sign pair composition - raw diagnostic counts, not efficiency"
    )
    pair_hist.GetYaxis().SetTitle("count")
    pair_hist.GetXaxis().SetTitle("")
    pair_hist.GetXaxis().LabelsOption("v")
    pair_hist.SetFillColor(root.TColor.GetColor("#3569a8"))
    pair_hist.SetLineColor(root.TColor.GetColor("#234a78"))
    pair_hist.SetBarWidth(0.38)
    pair_hist.SetBarOffset(0.10)
    event_hist.SetFillColor(root.TColor.GetColor("#e28a34"))
    event_hist.SetLineColor(root.TColor.GetColor("#a95918"))
    event_hist.SetBarWidth(0.38)
    event_hist.SetBarOffset(0.52)
    maximum = max(pair_hist.GetMaximum(), event_hist.GetMaximum(), 1.0)
    pair_hist.SetMinimum(0.0)
    pair_hist.SetMaximum(maximum * 1.28)
    pair_hist.Draw("BAR")
    event_hist.Draw("BAR SAME")
    legend = root.TLegend(0.69, 0.78, 0.95, 0.91)
    legend.SetBorderSize(0)
    legend.SetFillStyle(0)
    legend.AddEntry(pair_hist, "opposite-sign pairs", "f")
    legend.AddEntry(event_hist, "events with #geq1 such pair", "f")
    legend.Draw()
    note = root.TPaveText(0.10, 0.78, 0.59, 0.91, "NDC")
    note.SetFillColorAlpha(root.kWhite, 0.90)
    note.SetBorderSize(1)
    note.SetTextAlign(12)
    note.SetTextSize(0.032)
    note.AddText("Tag/probe means #geq1 member tagged; double-tag means both tagged.")
    note.AddText("No mass, acollinearity, acceptance, or background correction is applied.")
    note.Draw()
    canvas.Update()
    return canvas, [pair_hist, event_hist, legend, note]


def draw_mass_canvas(
    root: Any, histograms: Histograms, mass_diagnostics: Mapping[str, Any]
) -> Tuple[Any, List[Any]]:
    canvas = root.TCanvas(
        "opposite_sign_dilepton_mass_canvas", "OS dilepton mass", 1800, 760
    )
    canvas.Divide(2, 1, 0.002, 0.002)
    owned: List[Any] = []
    standard_color = root.TColor.GetColor("#3569a8")
    tight_color = root.TColor.GetColor("#d9782d")
    panels = (
        (
            histograms.dimuon_standard_mass,
            histograms.dimuon_tight_mass,
            "DATA (94c) - opposite-sign dimuon mass",
            "dimuon_standard",
            "dimuon_tight",
            "standard: both MUID bit 2; tight: both MUID bit 3",
            f"E=#sqrt{{p^{{2}}+m_{{#mu}}^{{2}}}}, m_{{#mu}}={MUON_MASS_GEV:.9f} GeV",
        ),
        (
            histograms.dielectron_standard_conversion_veto_mass,
            histograms.dielectron_tight_conversion_veto_mass,
            "DATA (94c) - opposite-sign dielectron mass",
            "dielectron_standard_conversion_veto",
            "dielectron_tight_conversion_veto",
            "standard: both ELID 4/5; tight: both ELID 5",
            f"E=#sqrt{{p^{{2}}+m_{{e}}^{{2}}}}, m_{{e}}={ELECTRON_MASS_GEV:.9f} GeV",
        ),
    )
    channel_counts = mass_diagnostics["channels"]
    for index, (
        standard,
        tight,
        title,
        standard_key,
        tight_key,
        selection,
        hypothesis,
    ) in enumerate(panels, 1):
        canvas.cd(index)
        root.gPad.SetLeftMargin(0.11)
        root.gPad.SetRightMargin(0.03)
        root.gPad.SetBottomMargin(0.12)
        root.gPad.SetTopMargin(0.12)
        root.gPad.SetLogy(True)
        standard.SetTitle(title)
        standard.SetMinimum(0.8)
        standard.SetMaximum(max(standard.GetMaximum(), tight.GetMaximum(), 1.0) * 12.0)
        standard.SetFillColorAlpha(standard_color, 0.48)
        standard.SetLineColor(standard_color)
        standard.SetLineWidth(2)
        standard.GetXaxis().SetTitleSize(0.045)
        standard.GetYaxis().SetTitleSize(0.043)
        standard.GetXaxis().SetLabelSize(0.038)
        standard.GetYaxis().SetLabelSize(0.038)
        standard.Draw("HIST")
        tight.SetLineColor(tight_color)
        tight.SetLineWidth(3)
        tight.SetFillStyle(0)
        tight.Draw("HIST SAME")
        legend = root.TLegend(0.58, 0.71, 0.94, 0.88)
        legend.SetBorderSize(0)
        legend.SetFillColorAlpha(root.kWhite, 0.86)
        legend.AddEntry(
            standard,
            f"standard ({channel_counts[standard_key]['pairs']:,} pairs)",
            "f",
        )
        legend.AddEntry(
            tight,
            f"tight ({channel_counts[tight_key]['pairs']:,} pairs)",
            "l",
        )
        legend.Draw()
        note = root.TPaveText(0.12, 0.64, 0.57, 0.89, "NDC")
        note.SetFillColorAlpha(root.kWhite, 0.88)
        note.SetBorderSize(1)
        note.SetTextAlign(12)
        note.SetTextSize(0.025)
        note.AddText(f"OS; p#geq{HIGH_P_GEV:g} GeV per particle")
        note.AddText(selection)
        if index == 2:
            note.AddText("conversion veto: both conversion tags = 0")
        note.AddText(hypothesis)
        if index == 2:
            note.AddText("track p only; no bremsstrahlung recovery")
        note.Draw()
        owned.extend((legend, note))
    canvas.Update()
    return canvas, owned


def runtime_version(module: str) -> str:
    try:
        return importlib.metadata.version(module)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def render_outputs(
    root: Any,
    temporary: Path,
    histograms: Histograms,
    provenance: Mapping[str, Any],
    summary: Mapping[str, Any],
    mass_diagnostics: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    root.gROOT.SetBatch(True)
    root.gStyle.SetOptStat(0)
    root.gStyle.SetPalette(root.kViridis)
    root.gStyle.SetNumberContours(255)
    root.gStyle.SetTitleFont(42, "XYZ")
    root.gStyle.SetLabelFont(42, "XYZ")
    root.gStyle.SetTextFont(42)
    root.gStyle.SetPaintTextFormat(".3g")

    target_canvas, target_owned = draw_target_canvas(root, histograms, summary)
    lepton_canvas, lepton_owned = draw_lepton_canvas(root, histograms)
    pair_canvas, pair_owned = draw_pair_canvas(root, histograms)
    mass_canvas, mass_owned = draw_mass_canvas(root, histograms, mass_diagnostics)
    canvases = (target_canvas, lepton_canvas, pair_canvas, mass_canvas)
    # Hold drawn helpers until every canvas has been serialized.
    owned = target_owned + lepton_owned + pair_owned + mass_owned
    if not owned:
        raise ValidationError("internal plotting ownership failure")

    png_names = (
        "target_response.png",
        "lepton_id_diagnostics.png",
        "high_p_os_pair_diagnostics.png",
        "opposite_sign_dilepton_mass.png",
    )
    for canvas, name in zip(canvases, png_names):
        canvas.SaveAs(str(temporary / name))
    pdf_path = temporary / "lepton_pid_validation.pdf"
    canvases[0].Print(f"{pdf_path}[")
    for canvas in canvases:
        canvas.Print(str(pdf_path))
    canvases[-1].Print(f"{pdf_path}]")

    root_path = temporary / "lepton_pid_validation.root"
    output = root.TFile.Open(str(root_path), "RECREATE", "DELPHI lepton PID validation", 9)
    if not output or output.IsZombie():
        raise ValidationError(f"cannot create ROOT artifact: {root_path}")
    try:
        response_directory = output.mkdir("target_response")
        response_directory.cd()
        for histogram in (histograms.dedx, histograms.rich_liquid, histograms.rich_gas):
            histogram.Write()
        id_directory = output.mkdir("lepton_id_diagnostics")
        id_directory.cd()
        for histogram in (
            histograms.muid_raw,
            histograms.muid_bits,
            histograms.elid_tag,
            histograms.elid_conversion,
            histograms.elid_tag_conversion,
        ):
            histogram.Write()
        pair_directory = output.mkdir("high_p_os_pair_diagnostics")
        pair_directory.cd()
        histograms.pair_counts.Write()
        histograms.pair_events.Write()
        mass_directory = output.mkdir("opposite_sign_dilepton_mass")
        mass_directory.cd()
        for histogram in (
            histograms.dimuon_standard_mass,
            histograms.dimuon_tight_mass,
            histograms.dielectron_standard_conversion_veto_mass,
            histograms.dielectron_tight_conversion_veto_mass,
        ):
            histogram.Write()
        output.cd()
        root.TObjString(json.dumps(provenance, sort_keys=True, allow_nan=False)).Write(
            "provenance_json"
        )
        root.TObjString(json.dumps(summary, sort_keys=True, allow_nan=False)).Write(
            "validated_summary_json"
        )
        root.TObjString(
            json.dumps(mass_diagnostics, sort_keys=True, allow_nan=False)
        ).Write("mass_diagnostics_json")
        for canvas in canvases:
            canvas.Write()
        output.Write()
    finally:
        output.Close()

    artifact_names = (*png_names, pdf_path.name, root_path.name)
    artifacts: Dict[str, Dict[str, Any]] = {}
    for name in artifact_names:
        path = temporary / name
        require_regular(path, "output artifact")
        artifacts[name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    return artifacts


def is_within(path: Path, directory: Path) -> bool:
    try:
        return os.path.commonpath((str(path), str(directory))) == str(directory)
    except ValueError:
        return False


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path, help="lolept94_c2 recalculated-only campaign")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--tape",
        action="append",
        default=[],
        metavar="Y13718.N",
        help="completed tape to plot; repeat for a deterministic subset",
    )
    selection.add_argument(
        "--all",
        action="store_true",
        help="require and process the complete official 132-tape campaign",
    )
    parser.add_argument("-o", "--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    temporary: Optional[Path] = None
    try:
        campaign, config, config_sha, manifest_sha, tapes = validate_campaign(
            args.campaign, args.tape, args.all
        )
        output_dir = args.output_dir.expanduser().resolve(strict=False)
        if output_dir == Path("/"):
            raise ValidationError("refusing to use / as output directory")
        if is_within(output_dir, campaign):
            raise ValidationError("output directory must be outside the live campaign")
        if output_dir.exists() or output_dir.is_symlink():
            raise ValidationError(f"output directory already exists: {output_dir}")
        output_dir.parent.mkdir(parents=True, exist_ok=True)

        try:
            import ROOT
            from podio import root_io
        except Exception as exc:
            raise ValidationError(
                "ROOT/podio are unavailable; run in Key4hep 2026-04-08 "
                f"({type(exc).__name__}: {exc})"
            ) from exc

        temporary = Path(
            tempfile.mkdtemp(prefix=f".{output_dir.name}.", suffix=".tmp", dir=str(output_dir.parent))
        )
        histograms = Histograms(ROOT)
        aggregate = Metrics()
        source_files: List[Dict[str, Any]] = []
        for index, tape in enumerate(tapes, 1):
            metrics = extract_tape(tape, root_io, histograms)
            aggregate.merge(metrics)
            current = tape.root.stat()
            if (
                current.st_size != tape.root_size
                or current.st_ino != tape.root_inode
                or current.st_mtime_ns != tape.root_mtime_ns
            ):
                raise ValidationError(f"{tape.root}: file changed before hashing")
            root_digest = sha256(tape.root)
            after_hash = tape.root.stat()
            if (
                after_hash.st_size != tape.root_size
                or after_hash.st_ino != tape.root_inode
                or after_hash.st_mtime_ns != tape.root_mtime_ns
            ):
                raise ValidationError(f"{tape.root}: file changed while hashing")
            if sha256(tape.marker) != tape.marker_sha256 or sha256(tape.audit) != tape.audit_sha256:
                raise ValidationError(f"{tape.tape}: marker or audit changed while plotting")
            source_files.append(
                {
                    "tape": tape.tape,
                    "events": tape.events,
                    "root": str(tape.root),
                    "root_bytes": tape.root_size,
                    "root_sha256": root_digest,
                    "completion_marker": str(tape.marker),
                    "completion_marker_sha256": tape.marker_sha256,
                    "audit": str(tape.audit),
                    "audit_sha256": tape.audit_sha256,
                }
            )
            print(f"validated={index}/{len(tapes)} tape={tape.tape} events={metrics.events}", flush=True)

        summary = aggregate.as_audit_json()
        if args.all and summary["events"] != EXPECTED_EVENTS:
            raise ValidationError(
                f"full campaign has {summary['events']} events, expected {EXPECTED_EVENTS}"
            )
        mass_diagnostics = validate_mass_histograms(histograms, summary)
        config_path = campaign / "campaign.conf"
        manifest_path = campaign / "inputs.manifest.tsv"
        if sha256(config_path) != config_sha or sha256(manifest_path) != manifest_sha:
            raise ValidationError("campaign configuration or manifest changed while plotting")

        script_path = Path(__file__).resolve(strict=True)
        provenance = {
            "dataset": DATASET,
            "scope": "full-132-tape-campaign" if args.all else "explicit-completed-tape-subset",
            "tapes": [tape.tape for tape in tapes],
            "production_policy": {
                "btag_mode": "recalc",
                "recalculated": True,
                "bank_production": "retired",
                "btag_provenance_schema": (
                    "legacy-frozen-v1"
                    if config["_input_contract"] == "exact-frozen-v1-campaign-sha256"
                    else "source-local-v1"
                ),
                "identity_source": "sDST_EVT",
                "input_contract": config["_input_contract"],
            },
            "campaign": str(campaign),
            "campaign_config_sha256": config_sha,
            "manifest_sha256": manifest_sha,
            "key4hep_release": config["key4hep_release"],
            "plotting_script": str(script_path),
            "plotting_script_sha256": sha256(script_path),
            "source_files": source_files,
            "selections": {
                "target_response": TARGET_SELECTIONS,
                "muid_standard": "raw bit mask & 0x4 != 0",
                "muid_tight": "raw bit mask & 0x8 != 0",
                "elid_standard": "tag in {4, 5}",
                "elid_tight": "tag == 5",
                "elid_conversion_veto": "conversion tag == 0",
                "opposite_sign_high_momentum": (
                    "both charged particles have p >= 20 GeV; no mass, acollinearity, "
                    "acceptance, or background correction"
                ),
                "dimuon_mass": (
                    "opposite-sign high-momentum double-tag pairs; standard has both "
                    "MUID bit 2 set, tight has both MUID bit 3 set; energy recomputed "
                    f"from the measured three-momentum with m_mu={MUON_MASS_GEV} GeV"
                ),
                "dielectron_mass": (
                    "opposite-sign high-momentum double-tag pairs with conversion tag 0 "
                    "on both particles; standard has both ELID tags in {4,5}, tight has "
                    "both tags equal to 5; energy recomputed from the measured "
                    f"three-momentum with m_e={ELECTRON_MASS_GEV} GeV"
                ),
            },
        }
        artifacts = render_outputs(
            ROOT, temporary, histograms, provenance, summary, mass_diagnostics
        )
        report = {
            "format": REPORT_FORMAT,
            "status": "PASS",
            "dataset": DATASET,
            "interpretation": {
                "target_response": "data detector-response population plots",
                "lepton_id": "diagnostic populations; not efficiency measurements",
                "opposite_sign_pairs": "diagnostic raw pair/event counts; not efficiency measurements",
                "opposite_sign_dilepton_mass": (
                    "track-momentum invariant-mass population diagnostics; no "
                    "acceptance, background, efficiency, or bremsstrahlung correction"
                ),
            },
            "determinism": {
                "random_sampling": False,
                "input_order": "numeric Y13718 tape number, then podio event/collection order",
                "fixed_histogram_binning": True,
                "wall_clock_timestamp_embedded_in_json": False,
            },
            "runtime": {
                "key4hep_release": config["key4hep_release"],
                "root": str(ROOT.gROOT.GetVersion()),
                "podio_python_distribution": runtime_version("podio"),
                "python": sys.version.split()[0],
            },
            "provenance": provenance,
            "validation": {
                "selected_tapes": len(tapes),
                "events_read": summary["events"],
                "all_exact_pid_relations_valid": (
                    summary["particle_id_contract"]["relations_checked"]
                    == summary["particle_id_contract"]["relations_valid"]
                ),
                "independent_counter_match_to_every_frozen_audit": True,
                "files_stable_during_read_and_hash": True,
                "mass_histograms_match_frozen_double_tag_pair_counts": True,
            },
            "summary": summary,
            "mass_diagnostics": mass_diagnostics,
            "artifacts": artifacts,
        }
        report_path = temporary / "lepton_pid_validation.json"
        write_text_atomic(report_path, canonical_json(report))
        report_sha = sha256(report_path)
        marker = {
            "format": COMPLETE_FORMAT,
            "status": "PASS",
            "dataset": DATASET,
            "btag_mode": "recalc",
            "recalculated": "1",
            "selected_tapes": str(len(tapes)),
            "events": str(summary["events"]),
            "report": report_path.name,
            "report_sha256": report_sha,
            "plotting_script_sha256": provenance["plotting_script_sha256"],
        }
        write_text_atomic(
            temporary / "validation.complete",
            "".join(f"{key}={value}\n" for key, value in marker.items()),
        )
        os.replace(temporary, output_dir)
        temporary = None
        print(
            f"status=PASS dataset={DATASET} tapes={len(tapes)} events={summary['events']} "
            f"btag_mode=recalc output={output_dir} report_sha256={report_sha}"
        )
        return 0
    except (ValidationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
