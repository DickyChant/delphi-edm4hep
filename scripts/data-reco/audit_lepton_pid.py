#!/usr/bin/env python3
"""Fail-closed lepton-PID and target-response audit for EDM4hep files.

The audit reads every event in every input file.  It verifies the four sDST
ParticleID collections used by the DELPHI lepton/PID checks, including their
Particle relations and fixed parameter-vector contracts.  It also reports the
raw MUCAL2 bit masks, ELECID/conversion tags, high-momentum opposite-sign pair
diagnostics, and the dE/dx/RICH populations used by target.pdf pages 9--11.

Exit status is zero only when every requested file was read completely and no
contract failure was found.  Physics-population counters are diagnostic and do
not themselves determine PASS/FAIL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import math
import os
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


REPORT_FORMAT = "delphi-edm4hep-lepton-pid-audit-v1"
PARTICLE_COLLECTION = "sDST_MAIN_Particles"

# collection: (expected algorithmType, exact parameter count)
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


def sorted_counter(counter: Counter[Any]) -> Dict[str, int]:
    """Return a deterministic, JSON-friendly representation of a Counter."""

    def order(item: Tuple[Any, int]) -> Tuple[int, Any]:
        key = item[0]
        if isinstance(key, int):
            return (0, key)
        return (1, str(key))

    return {str(key): int(value) for key, value in sorted(counter.items(), key=order)}


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
        self.events += other.events
        self.particles += other.particles
        self.parameter_vectors_checked += other.parameter_vectors_checked
        self.relations_checked += other.relations_checked
        self.relations_valid += other.relations_valid
        self.electron_conversion_veto_rows += other.electron_conversion_veto_rows
        self.electron_standard_rows += other.electron_standard_rows
        self.electron_standard_conversion_veto_rows += (
            other.electron_standard_conversion_veto_rows
        )
        self.electron_undocumented_tag_rows += other.electron_undocumented_tag_rows
        self.electron_undocumented_conversion_rows += (
            other.electron_undocumented_conversion_rows
        )
        for name in (
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
            getattr(self, name).update(getattr(other, name))

    def as_json(self, high_p_gev: float) -> Dict[str, Any]:
        rows = {name: int(self.collection_rows[name]) for name in REQUIRED_COLLECTIONS}
        muon_bits = {name: int(self.muon_bit_counts[name]) for name, _ in MUID_BITS}
        pairs = {
            name: {
                "pairs": int(self.pair_counts[name]),
                "events_with_at_least_one_pair": int(self.pair_events[name]),
            }
            for name in PAIR_CATEGORIES
        }
        return {
            "events": self.events,
            "particles": self.particles,
            "collection_rows": rows,
            "particle_id_contract": {
                "parameter_vectors_checked": self.parameter_vectors_checked,
                "relations_checked": self.relations_checked,
                "relations_valid": self.relations_valid,
            },
            "muon_id": {
                "raw_tag_distribution": sorted_counter(self.muon_raw_tags),
                "set_bit_counts": muon_bits,
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
                "undocumented_tag_outside_1_to_5_rows": self.electron_undocumented_tag_rows,
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
                "minimum_momentum_gev_per_particle": high_p_gev,
                "categories": pairs,
            },
        }


@dataclass
class FailureRecorder:
    sample_limit: int
    counts: Counter[str] = field(default_factory=Counter)
    samples: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, code: str, event_index: Optional[int], detail: str) -> None:
        self.counts[code] += 1
        if len(self.samples) < self.sample_limit:
            sample: Dict[str, Any] = {"code": code, "detail": detail}
            if event_index is not None:
                sample["event_index"] = event_index
            self.samples.append(sample)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def merge(self, other: "FailureRecorder", path: str) -> None:
        self.counts.update(other.counts)
        for sample in other.samples:
            if len(self.samples) >= self.sample_limit:
                break
            copied = dict(sample)
            copied["file"] = path
            self.samples.append(copied)

    def as_json(self) -> Dict[str, Any]:
        return {
            "count": self.total,
            "codes": sorted_counter(self.counts),
            "samples": self.samples,
            "samples_truncated": self.total > len(self.samples),
        }


@dataclass(frozen=True)
class ParticleInfo:
    charge: float
    momentum: float


def object_key(obj: Any) -> Tuple[int, int]:
    oid = obj.getObjectID()
    return int(oid.collectionID), int(oid.index)


def finite_parameters(
    values: Sequence[float],
    collection: str,
    event_index: int,
    failures: FailureRecorder,
) -> bool:
    good = True
    for index, value in enumerate(values):
        if not math.isfinite(value):
            failures.add(
                "nonfinite_parameter",
                event_index,
                f"{collection} parameter[{index}] is {value!r}",
            )
            good = False
    return good


def integral_parameter(
    value: float,
    collection: str,
    parameter: int,
    event_index: int,
    failures: FailureRecorder,
) -> Optional[int]:
    rounded = int(round(value))
    if abs(value - rounded) > 1.0e-5:
        failures.add(
            "nonintegral_integer_parameter",
            event_index,
            f"{collection} parameter[{parameter}]={value!r}",
        )
        return None
    return rounded


def relation_key(
    pid: Any,
    collection: str,
    particle_info: Mapping[Tuple[int, int], ParticleInfo],
    event_index: int,
    failures: FailureRecorder,
    metrics: Metrics,
) -> Optional[Tuple[int, int]]:
    metrics.relations_checked += 1
    try:
        particle = pid.getParticle()
        if not particle.isAvailable():
            raise ValueError("relation is unavailable")
        key = object_key(particle)
    except Exception as exc:
        failures.add(
            "unresolved_particle_relation",
            event_index,
            f"{collection}: {exc}",
        )
        return None
    if key not in particle_info:
        failures.add(
            "particle_relation_wrong_collection_or_index",
            event_index,
            f"{collection} points to ObjectID(collection={key[0]}, index={key[1]})",
        )
        return None
    if particle_info[key].charge == 0.0:
        failures.add(
            "particle_relation_targets_neutral",
            event_index,
            f"{collection} points to neutral ObjectID(collection={key[0]}, index={key[1]})",
        )
        return None
    metrics.relations_valid += 1
    return key


def audit_pid_collection(
    collection_name: str,
    collection: Iterable[Any],
    particle_info: Mapping[Tuple[int, int], ParticleInfo],
    event_index: int,
    failures: FailureRecorder,
    metrics: Metrics,
    muon_tags: Dict[Tuple[int, int], int],
    electron_tags: Dict[Tuple[int, int], Tuple[int, int]],
) -> None:
    expected_algorithm, expected_parameters = PID_SPECS[collection_name]
    seen_relations: set[Tuple[int, int]] = set()

    try:
        rows = list(collection)
    except Exception as exc:
        failures.add(
            "collection_iteration_failure",
            event_index,
            f"{collection_name}: {exc}",
        )
        return

    metrics.collection_rows[collection_name] += len(rows)
    for row_index, pid in enumerate(rows):
        try:
            algorithm = int(pid.getAlgorithmType())
        except Exception as exc:
            failures.add(
                "algorithm_type_read_failure",
                event_index,
                f"{collection_name}[{row_index}]: {exc}",
            )
            algorithm = None
        if algorithm is not None and algorithm != expected_algorithm:
            failures.add(
                "wrong_algorithm_type",
                event_index,
                f"{collection_name}[{row_index}] has {algorithm}, expected {expected_algorithm}",
            )

        try:
            parameters = [float(value) for value in pid.getParameters()]
        except Exception as exc:
            failures.add(
                "parameter_vector_read_failure",
                event_index,
                f"{collection_name}[{row_index}]: {exc}",
            )
            parameters = []
        metrics.parameter_vectors_checked += 1
        length_ok = len(parameters) == expected_parameters
        if not length_ok:
            failures.add(
                "wrong_parameter_count",
                event_index,
                f"{collection_name}[{row_index}] has {len(parameters)}, expected {expected_parameters}",
            )
        values_finite = finite_parameters(
            parameters, collection_name, event_index, failures
        )

        key = relation_key(
            pid,
            collection_name,
            particle_info,
            event_index,
            failures,
            metrics,
        )
        if key is not None:
            if key in seen_relations:
                failures.add(
                    "duplicate_particle_relation",
                    event_index,
                    f"{collection_name} has more than one row for ObjectID{key}",
                )
                key = None
            else:
                seen_relations.add(key)

        if not length_ok or not values_finite:
            continue

        if collection_name == "sDST_MUID_MuonID":
            tag = integral_parameter(
                parameters[0], collection_name, 0, event_index, failures
            )
            # parameters[2] is also an integer-valued hit-pattern word.
            integral_parameter(
                parameters[2], collection_name, 2, event_index, failures
            )
            if tag is None:
                continue
            metrics.muon_raw_tags[tag] += 1
            if tag <= 0 or tag & ~MUID_KNOWN_MASK:
                failures.add(
                    "invalid_muid_bitmask",
                    event_index,
                    f"{collection_name}[{row_index}] raw tag={tag}",
                )
                continue
            for name, bit in MUID_BITS:
                if tag & (1 << bit):
                    metrics.muon_bit_counts[name] += 1
            if key is not None:
                muon_tags[key] = tag

        elif collection_name == "sDST_ELID_ElectronID":
            tag = integral_parameter(
                parameters[0], collection_name, 0, event_index, failures
            )
            conversion = integral_parameter(
                parameters[1], collection_name, 1, event_index, failures
            )
            if tag is None or conversion is None:
                continue
            metrics.electron_tags[tag] += 1
            metrics.electron_conversion_tags[conversion] += 1
            metrics.electron_tag_by_conversion[f"tag={tag},conversion={conversion}"] += 1
            # ELECID documents tag levels 1..5 and conversion levels 0..3.
            # Real 94c data contains rare other integer-valued conversion
            # payloads. Preserve and report undocumented values without ever
            # promoting them into a documented electron working point.
            if tag < 1 or tag > 9:
                failures.add(
                    "invalid_elid_tag",
                    event_index,
                    f"{collection_name}[{row_index}] tag={tag}",
                )
                continue
            if conversion < 0 or conversion > 9:
                failures.add(
                    "invalid_elid_conversion_tag",
                    event_index,
                    f"{collection_name}[{row_index}] conversion tag={conversion}",
                )
                continue
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
            if key is not None:
                electron_tags[key] = (tag, conversion)

        elif collection_name == "sDST_HAID_dEdx":
            dedx, sigma = parameters
            metrics.dedx["valid_rows"] += 1
            metrics.dedx["positive" if dedx > 0.0 else "nonpositive"] += 1
            metrics.dedx[
                "sigma_nonnegative" if sigma >= 0.0 else "sigma_negative"
            ] += 1
            if (
                key is not None
                and particle_info[key].momentum > 0.0
                and dedx > 0.0
            ):
                metrics.dedx["target_plot_eligible"] += 1

        elif collection_name == "sDST_HAID_HadronID":
            gas_theta, gas_nph, gas_flag_value = (
                parameters[8],
                parameters[10],
                parameters[12],
            )
            liquid_theta, liquid_nph, liquid_flag_value = (
                parameters[13],
                parameters[15],
                parameters[17],
            )
            gas_nph_int = integral_parameter(
                gas_nph, collection_name, 10, event_index, failures
            )
            gas_flag = integral_parameter(
                gas_flag_value, collection_name, 12, event_index, failures
            )
            liquid_nph_int = integral_parameter(
                liquid_nph, collection_name, 15, event_index, failures
            )
            liquid_flag = integral_parameter(
                liquid_flag_value, collection_name, 17, event_index, failures
            )
            if gas_nph_int is not None and gas_nph_int < 0:
                failures.add(
                    "invalid_rich_n_photoelectrons",
                    event_index,
                    f"{collection_name}[{row_index}] gas Npe={gas_nph_int}",
                )
                gas_nph_int = None
            if liquid_nph_int is not None and liquid_nph_int < 0:
                failures.add(
                    "invalid_rich_n_photoelectrons",
                    event_index,
                    f"{collection_name}[{row_index}] liquid Npe={liquid_nph_int}",
                )
                liquid_nph_int = None
            if gas_flag is not None and (gas_flag < 0 or gas_flag & ~0x3F):
                failures.add(
                    "invalid_rich_quality_word",
                    event_index,
                    f"{collection_name}[{row_index}] gas FLAGG={gas_flag}",
                )
                gas_flag = None
            if liquid_flag is not None and (
                liquid_flag < 0 or liquid_flag & ~0x3F
            ):
                failures.add(
                    "invalid_rich_quality_word",
                    event_index,
                    f"{collection_name}[{row_index}] liquid FLAGL={liquid_flag}",
                )
                liquid_flag = None
            if gas_nph_int is not None and gas_flag is not None:
                audit_rich_row(
                    gas_theta,
                    gas_nph_int,
                    gas_flag,
                    key,
                    particle_info,
                    metrics.rich_gas,
                    metrics.rich_gas_flags,
                    required_flag_mask=0x0F,
                )
            if liquid_nph_int is not None and liquid_flag is not None:
                audit_rich_row(
                    liquid_theta,
                    liquid_nph_int,
                    liquid_flag,
                    key,
                    particle_info,
                    metrics.rich_liquid,
                    metrics.rich_liquid_flags,
                    required_flag_mask=None,
                )


def audit_rich_row(
    theta: float,
    n_photoelectrons: int,
    flag: int,
    key: Optional[Tuple[int, int]],
    particle_info: Mapping[Tuple[int, int], ParticleInfo],
    counters: Counter[str],
    flag_distribution: Counter[int],
    required_flag_mask: Optional[int],
) -> None:
    counters["valid_rows"] += 1
    flag_distribution[flag] += 1
    theta_ok = theta > 0.0
    photons_ok = n_photoelectrons >= 3
    flag_ok = (
        (flag & required_flag_mask) == required_flag_mask
        if required_flag_mask is not None
        else flag != 0
    )
    if theta_ok:
        counters["theta_positive"] += 1
    if photons_ok:
        counters["n_photoelectrons_ge_3"] += 1
    if flag_ok:
        counters["quality_flag_pass"] += 1
    if flag != 0:
        counters["flag_nonzero"] += 1
    if theta_ok and photons_ok:
        counters["theta_positive_and_n_photoelectrons_ge_3"] += 1
    if (
        theta_ok
        and photons_ok
        and flag_ok
        and key is not None
        and particle_info[key].momentum > 0.0
    ):
        counters["target_plot_eligible"] += 1


def audit_pairs(
    particle_info: Mapping[Tuple[int, int], ParticleInfo],
    muon_tags: Mapping[Tuple[int, int], int],
    electron_tags: Mapping[Tuple[int, int], Tuple[int, int]],
    high_p_gev: float,
    metrics: Metrics,
) -> None:
    candidates = [
        (key, info)
        for key, info in particle_info.items()
        if info.momentum >= high_p_gev and info.charge != 0.0
    ]
    event_categories: set[str] = set()
    for first in range(len(candidates)):
        key_a, particle_a = candidates[first]
        for second in range(first + 1, len(candidates)):
            key_b, particle_b = candidates[second]
            if particle_a.charge * particle_b.charge >= 0.0:
                continue

            mu_a = muon_tags.get(key_a, 0)
            mu_b = muon_tags.get(key_b, 0)
            el_a = electron_tags.get(key_a, (0, -1))
            el_b = electron_tags.get(key_b, (0, -1))

            mu_standard_a = bool(mu_a & (1 << 2))
            mu_standard_b = bool(mu_b & (1 << 2))
            mu_tight_a = bool(mu_a & (1 << 3))
            mu_tight_b = bool(mu_b & (1 << 3))
            el_standard_a = el_a[0] in (4, 5)
            el_standard_b = el_b[0] in (4, 5)
            el_standard_veto_a = el_standard_a and el_a[1] == 0
            el_standard_veto_b = el_standard_b and el_b[1] == 0
            el_tight_veto_a = el_a[0] == 5 and el_a[1] == 0
            el_tight_veto_b = el_b[0] == 5 and el_b[1] == 0

            decisions = {
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
            for name, accepted in decisions.items():
                if accepted:
                    metrics.pair_counts[name] += 1
                    event_categories.add(name)
    for name in event_categories:
        metrics.pair_events[name] += 1


def audit_frame(
    frame: Any,
    event_index: int,
    high_p_gev: float,
    failures: FailureRecorder,
    metrics: Metrics,
) -> None:
    try:
        available = set(frame.getAvailableCollections())
    except Exception as exc:
        failures.add("collection_inventory_failure", event_index, str(exc))
        return

    missing = [name for name in REQUIRED_COLLECTIONS if name not in available]
    for name in missing:
        failures.add("missing_required_collection", event_index, name)

    particle_info: Dict[Tuple[int, int], ParticleInfo] = {}
    if PARTICLE_COLLECTION in available:
        try:
            particles = frame.get(PARTICLE_COLLECTION)
            particle_rows = list(particles)
            metrics.collection_rows[PARTICLE_COLLECTION] += len(particle_rows)
            metrics.particles += len(particle_rows)
            for row_index, particle in enumerate(particle_rows):
                key = object_key(particle)
                if key in particle_info:
                    failures.add(
                        "duplicate_particle_object_id",
                        event_index,
                        f"{PARTICLE_COLLECTION}[{row_index}] ObjectID{key}",
                    )
                    continue
                momentum = particle.getMomentum()
                px, py, pz = float(momentum.x), float(momentum.y), float(momentum.z)
                charge = float(particle.getCharge())
                magnitude = math.sqrt(px * px + py * py + pz * pz)
                if not all(math.isfinite(value) for value in (px, py, pz, charge)):
                    failures.add(
                        "nonfinite_particle_kinematics",
                        event_index,
                        f"{PARTICLE_COLLECTION}[{row_index}]",
                    )
                    continue
                particle_info[key] = ParticleInfo(charge=charge, momentum=magnitude)
        except Exception as exc:
            failures.add(
                "particle_collection_read_failure",
                event_index,
                f"{PARTICLE_COLLECTION}: {exc}",
            )

    muon_tags: Dict[Tuple[int, int], int] = {}
    electron_tags: Dict[Tuple[int, int], Tuple[int, int]] = {}
    for collection_name in PID_SPECS:
        if collection_name not in available:
            continue
        try:
            collection = frame.get(collection_name)
        except Exception as exc:
            failures.add(
                "collection_read_failure",
                event_index,
                f"{collection_name}: {exc}",
            )
            continue
        audit_pid_collection(
            collection_name,
            collection,
            particle_info,
            event_index,
            failures,
            metrics,
            muon_tags,
            electron_tags,
        )
    audit_pairs(particle_info, muon_tags, electron_tags, high_p_gev, metrics)


def audit_file(
    path: Path, high_p_gev: float, sample_limit: int, root_io: Any
) -> Tuple[Metrics, FailureRecorder]:
    metrics = Metrics()
    failures = FailureRecorder(sample_limit=sample_limit)
    try:
        frames = root_io.Reader(str(path)).get("events")
        for event_index, frame in enumerate(frames):
            metrics.events += 1
            audit_frame(frame, event_index, high_p_gev, failures, metrics)
    except Exception as exc:
        failures.add("file_read_failure", None, f"{type(exc).__name__}: {exc}")
    if metrics.events == 0:
        failures.add("empty_event_stream", None, "events frame category has zero entries")
    return metrics, failures


def read_manifest(path_text: str) -> List[Tuple[str, Path]]:
    path = Path(os.path.expanduser(path_text)).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"manifest is not a regular file: {path}")
    entries: List[Tuple[str, Path]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        token = raw.strip()
        if not token or token.startswith("#"):
            continue
        if "\0" in token:
            raise ValueError(f"NUL in {path}:{line_number}")
        entries.append((token, path.parent))
    if not entries:
        raise ValueError(f"manifest contains no file entries: {path}")
    return entries


def expand_input(token: str, base: Path) -> List[Path]:
    expanded = os.path.expanduser(token)
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = base / candidate
    pattern = str(candidate)
    if glob.has_magic(pattern):
        matches = [Path(match) for match in glob.glob(pattern, recursive=True)]
        if not matches:
            raise ValueError(f"input glob matched no files: {token}")
        return matches
    return [candidate]


def resolve_inputs(inputs: Sequence[str], manifests: Sequence[str]) -> List[Path]:
    specifications: List[Tuple[str, Path]] = []
    cwd = Path.cwd()
    for token in inputs:
        if token.startswith("@"):
            if token == "@":
                raise ValueError("empty @manifest argument")
            specifications.extend(read_manifest(token[1:]))
        else:
            specifications.append((token, cwd))
    for manifest in manifests:
        specifications.extend(read_manifest(manifest))
    if not specifications:
        raise ValueError("provide at least one ROOT file/glob or --manifest")

    resolved: Dict[str, Path] = {}
    for token, base in specifications:
        for candidate in expand_input(token, base):
            try:
                path = candidate.resolve(strict=True)
            except FileNotFoundError as exc:
                raise ValueError(f"input does not exist: {candidate}") from exc
            if not path.is_file():
                raise ValueError(f"input is not a regular file: {path}")
            if path.stat().st_size <= 0:
                raise ValueError(f"input is empty: {path}")
            resolved[str(path)] = path
    return [resolved[key] for key in sorted(resolved)]


def write_json(report: Mapping[str, Any], output: str) -> None:
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output == "-":
        sys.stdout.write(payload)
        return
    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def error_report(message: str) -> Dict[str, Any]:
    return {
        "format": REPORT_FORMAT,
        "status": "ERROR",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "error": message,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit converted DELPHI EDM4hep ROOT files for lepton PID and "
            "target.pdf dE/dx/RICH response contracts."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="ROOT files, quoted globs, or @MANIFEST (one path/glob per line)",
    )
    parser.add_argument(
        "--manifest",
        action="append",
        default=[],
        metavar="PATH",
        help="read paths/globs from PATH; may be repeated",
    )
    parser.add_argument(
        "--output",
        default="-",
        metavar="JSON",
        help="JSON report path, or - for stdout (default: -)",
    )
    parser.add_argument(
        "--high-p-gev",
        type=float,
        default=20.0,
        help="per-particle momentum threshold for OS diagnostics (default: 20)",
    )
    parser.add_argument(
        "--failure-samples",
        type=int,
        default=50,
        help="maximum failure examples retained in the JSON report (default: 50)",
    )
    args = parser.parse_args(argv)
    if not math.isfinite(args.high_p_gev) or args.high_p_gev < 0.0:
        parser.error("--high-p-gev must be finite and nonnegative")
    if args.failure_samples < 0:
        parser.error("--failure-samples must be nonnegative")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        paths = resolve_inputs(args.inputs, args.manifest)
    except Exception as exc:
        report = error_report(f"input resolution failed: {exc}")
        write_json(report, args.output)
        return 2

    if args.output != "-":
        destination = Path(args.output).expanduser().resolve()
        aliases_input = destination in paths
        if destination.exists():
            aliases_input = aliases_input or any(
                os.path.samefile(destination, path) for path in paths
            )
        if aliases_input:
            print(
                f"ERROR: refusing to overwrite input ROOT file with JSON: {destination}",
                file=sys.stderr,
            )
            return 2

    try:
        from podio import root_io
    except Exception as exc:
        report = error_report(
            "podio Python bindings are unavailable; source the pinned key4hep "
            f"environment before running ({type(exc).__name__}: {exc})"
        )
        write_json(report, args.output)
        return 2

    aggregate_metrics = Metrics()
    aggregate_failures = FailureRecorder(sample_limit=args.failure_samples)
    file_reports: List[Dict[str, Any]] = []
    for path in paths:
        metrics, failures = audit_file(
            path, args.high_p_gev, args.failure_samples, root_io
        )
        aggregate_metrics.merge(metrics)
        aggregate_failures.merge(failures, str(path))
        file_reports.append(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "status": "PASS" if failures.total == 0 else "FAIL",
                "metrics": metrics.as_json(args.high_p_gev),
                "failures": failures.as_json(),
            }
        )

    status = "PASS" if aggregate_failures.total == 0 else "FAIL"
    report = {
        "format": REPORT_FORMAT,
        "status": status,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "configuration": {
            "required_collections": {
                PARTICLE_COLLECTION: {"role": "ParticleID relation target"},
                **{
                    name: {
                        "algorithm_type": algorithm,
                        "parameter_count": count,
                    }
                    for name, (algorithm, count) in PID_SPECS.items()
                },
            },
            "muid_raw_bitmask": {
                name: {"bit": bit, "mask": 1 << bit} for name, bit in MUID_BITS
            },
            "electron_id": {
                "standard_or_tighter": "tag in {4, 5}",
                "tight": "tag == 5",
                "conversion_veto": "conversion tag == 0",
            },
            "target_response_selections": {
                "dedx": "parameters[0] > 0 and linked particle momentum > 0",
                "rich_gas": (
                    "parameters[8] > 0, parameters[10] >= 3, "
                    "all low four quality bits of parameters[12] set, and "
                    "linked particle momentum > 0"
                ),
                "rich_liquid": (
                    "parameters[13] > 0, parameters[15] >= 3, "
                    "parameters[17] != 0, and linked particle momentum > 0"
                ),
            },
            "opposite_sign_high_momentum_diagnostics": {
                "minimum_momentum_gev_per_particle": args.high_p_gev,
                "tag_probe": "at least one member of the pair passes the named tag",
                "double_tag": "both members of the pair pass the named tag",
                "note": "diagnostic counts only; no invariant-mass or acollinearity cut",
            },
        },
        "inputs": {
            "file_count": len(paths),
            "total_size_bytes": sum(path.stat().st_size for path in paths),
            "files": [str(path) for path in paths],
        },
        "summary": aggregate_metrics.as_json(args.high_p_gev),
        "failures": aggregate_failures.as_json(),
        "files": file_reports,
    }
    write_json(report, args.output)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
