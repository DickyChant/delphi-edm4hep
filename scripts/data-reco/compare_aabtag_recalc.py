#!/usr/bin/env python3
"""Strict same-event comparison of two recalculated AABTAG productions.

Files are paired by basename when two directories are supplied (or directly
when two files are supplied).  Within each source-file pair, events are joined
by the exact ``(runNumber, eventNumber, fileSeq)`` key; entry position is never
used as the join key.  The comparator covers the AABTAG probability triplets,
thrust, status/count metadata, all parallel AABTAG track arrays, and the
primary-vertex/beamspot/track inputs relevant to b tagging.

Differences are measurements, not an automatic failure.  Structural/schema,
provenance, duplicate-key, or key-set errors always fail.  Pass
``--require-exact`` to also make any common-field value difference fail.  The
legacy compatibility flag permits only the four fields introduced after the
first recalculated campaign (``BadEventCode``, ``AlgorithmInvoked``, ``Valid``,
and ``NTracksRaw``) to be absent on the left; their absence is reported and is
never silently converted to a value.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from report_destination import (
    ReportDestinationError,
    atomic_write_report_text,
    lexical_absolute,
    validate_report_destination,
)


EventKey = Tuple[int, int, int]
MISSING = object()
PROBABILITY_COMPONENTS = ("hemisphere_1", "hemisphere_2", "event")
AXIS_COMPONENTS = ("x", "y", "z")

STRING_PARAMETERS = (
    "sDST_BTAGCFG_Mode",
)

INTEGER_PARAMETERS = (
    "sDST_BTAGCFG_Recalculated",
    "sDST_EVT_hadronicTagTeam4",
    "sDST_EVT_nChargedTeam4",
    "sDST_EVT_nCharged",
    "sDST_EVT_BeamSpotErrorCode",
    "sDST_AABTAG_NTracks",
    "sDST_AABTAG_NTracksAttached",
    "sDST_AABTAG_Truncated",
)

LEGACY_OPTIONAL_INTEGER_PARAMETERS = (
    "sDST_AABTAG_BadEventCode",
    "sDST_AABTAG_AlgorithmInvoked",
    "sDST_AABTAG_Valid",
    "sDST_AABTAG_NTracksRaw",
)

FLOAT_PARAMETERS = (
    "sDST_AABTAG_ThrustValue",
    "sDST_EVT_BeamSpotX",
    "sDST_EVT_BeamSpotY",
    "sDST_EVT_BeamSpotZ",
    "sDST_EVT_BeamSpotSigmaX",
    "sDST_EVT_BeamSpotSigmaY",
    "sDST_EVT_BeamSpotSigmaZ",
)

FLOAT_VECTOR3_PARAMETERS = (
    "sDST_AABTAG_ProbNegIP",
    "sDST_AABTAG_ProbPosIP",
    "sDST_AABTAG_ProbAllIP",
    "sDST_AABTAG_ThrustAxis",
)

AABTAG_INTEGER_COLLECTIONS = (
    "sDST_AABTAG_Tracks_ParticleIndex",
    "sDST_AABTAG_Tracks_UsedForTag",
    "sDST_AABTAG_Tracks_AttachedToPV",
    "sDST_AABTAG_Tracks_NVDHitsRPhi",
    "sDST_AABTAG_Tracks_NVDHitsZ",
    "sDST_AABTAG_Tracks_NVDLayersRPhi",
    "sDST_AABTAG_Tracks_NVDLayersZ",
)

AABTAG_FLOAT_COLLECTIONS = (
    "sDST_AABTAG_Tracks_ImpactParRPhi",
    "sDST_AABTAG_Tracks_ImpactParRPhiError",
    "sDST_AABTAG_Tracks_ImpactParZ",
    "sDST_AABTAG_Tracks_ImpactParZError",
    "sDST_AABTAG_Tracks_ProbRPhi",
    "sDST_AABTAG_Tracks_ProbZ",
    "sDST_AABTAG_Tracks_Chi2VD",
    "sDST_AABTAG_Tracks_Chi2PV",
    "sDST_AABTAG_Tracks_Momentum",
)

PV_TRACK_INTEGER_COLLECTIONS = (
    "sDST_PV_trackImpactFlag",
    "sDST_PV_Vertices_StatusBits",
    "sDST_VECP_LVLOCK",
)

PV_TRACK_FLOAT_COLLECTIONS = (
    "sDST_PV_trackD0PV",
    "sDST_PV_trackZ0PV",
    "sDST_TRAC_d0PV",
    "sDST_TRAC_z0PV",
    "sDST_TRAC_d0BS",
)

VERTEX_COLLECTIONS = (
    "sDST_AABTAG_PrimaryVertex",
    "sDST_PV_PrimaryVertex",
    "sDST_PV_Vertices",
    "sDST_BSP_BeamSpot",
)

SIZE_ONLY_COLLECTIONS = (
    "sDST_MAIN_Particles",
    "sDST_TRAC_Tracks",
)

VERTEX_ATTRIBUTES = (
    "isPrimary",
    "algorithmType",
    "chi2",
    "ndf",
    "position_x",
    "position_y",
    "position_z",
    "cov_xx",
    "cov_xy",
    "cov_yy",
    "cov_xz",
    "cov_yz",
    "cov_zz",
)

def json_value(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "+Infinity" if value > 0.0 else "-Infinity"
    return value


def exact_value_equal(left: Any, right: Any) -> bool:
    if isinstance(left, float) or isinstance(right, float):
        left_float = float(left)
        right_float = float(right)
        if math.isnan(left_float) and math.isnan(right_float):
            return True
        return left_float == right_float
    return left == right


@dataclass
class FieldComparison:
    name: str
    max_examples: int
    events_seen: int = 0
    events_both_present: int = 0
    events_value_different: int = 0
    presence_mismatch_events: int = 0
    length_mismatch_events: int = 0
    observations_compared: int = 0
    observations_different: int = 0
    exact_equal_observations: int = 0
    finite_numeric_observations: int = 0
    both_nan_observations: int = 0
    nonfinite_mismatch_observations: int = 0
    max_abs_difference: Optional[float] = None

    def __post_init__(self) -> None:
        self.first_differences: List[Dict[str, Any]] = []
        self.value_changed_keys: Set[EventKey] = set()
        self.presence_changed_keys: Set[EventKey] = set()

    def _record_difference(
        self,
        key: EventKey,
        left: Any,
        right: Any,
        index: Optional[int],
        reason: str,
    ) -> None:
        if len(self.first_differences) >= self.max_examples:
            return
        item: Dict[str, Any] = {
            "key": list(key),
            "left": json_value(left),
            "right": json_value(right),
            "reason": reason,
        }
        if index is not None:
            item["index"] = index
        self.first_differences.append(item)

    def _compare_observation(
        self, key: EventKey, left: Any, right: Any, index: Optional[int]
    ) -> bool:
        self.observations_compared += 1
        finite_pair = False
        try:
            left_float = float(left)
            right_float = float(right)
            finite_pair = math.isfinite(left_float) and math.isfinite(right_float)
            if finite_pair:
                self.finite_numeric_observations += 1
                difference = abs(right_float - left_float)
                if (
                    self.max_abs_difference is None
                    or difference > self.max_abs_difference
                ):
                    self.max_abs_difference = difference
        except (TypeError, ValueError):
            pass
        if exact_value_equal(left, right):
            self.exact_equal_observations += 1
            if (
                isinstance(left, float)
                and isinstance(right, float)
                and math.isnan(left)
                and math.isnan(right)
            ):
                self.both_nan_observations += 1
            return True

        self.observations_different += 1
        if not finite_pair and (
            isinstance(left, (int, float)) or isinstance(right, (int, float))
        ):
            self.nonfinite_mismatch_observations += 1
        self._record_difference(
            key,
            left,
            right,
            index,
            "value" if finite_pair else "value_or_finiteness",
        )
        return False

    def add_scalar(self, key: EventKey, left: Any, right: Any) -> None:
        self.events_seen += 1
        if left is MISSING or right is MISSING:
            self.presence_mismatch_events += int(left is MISSING) ^ int(
                right is MISSING
            )
            if left is MISSING and right is MISSING:
                return
            self._record_difference(
                key,
                "MISSING" if left is MISSING else left,
                "MISSING" if right is MISSING else right,
                None,
                "presence",
            )
            self.presence_changed_keys.add(key)
            return
        self.events_both_present += 1
        if not self._compare_observation(key, left, right, None):
            self.events_value_different += 1
            self.value_changed_keys.add(key)

    def add_sequence(self, key: EventKey, left: Any, right: Any) -> None:
        self.events_seen += 1
        if left is MISSING or right is MISSING:
            self.presence_mismatch_events += int(left is MISSING) ^ int(
                right is MISSING
            )
            if left is MISSING and right is MISSING:
                return
            self._record_difference(
                key,
                "MISSING" if left is MISSING else f"len={len(left)}",
                "MISSING" if right is MISSING else f"len={len(right)}",
                None,
                "presence",
            )
            self.presence_changed_keys.add(key)
            return
        self.events_both_present += 1
        event_different = False
        if len(left) != len(right):
            self.length_mismatch_events += 1
            event_different = True
            self._record_difference(
                key, len(left), len(right), None, "length"
            )
        for index, (left_value, right_value) in enumerate(zip(left, right)):
            if not self._compare_observation(
                key, left_value, right_value, index
            ):
                event_different = True
        if event_different:
            self.events_value_different += 1
            self.value_changed_keys.add(key)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "events_seen": self.events_seen,
            "events_both_present": self.events_both_present,
            "events_value_different": self.events_value_different,
            "presence_mismatch_events": self.presence_mismatch_events,
            "length_mismatch_events": self.length_mismatch_events,
            "observations_compared": self.observations_compared,
            "exact_equal_observations": self.exact_equal_observations,
            "observations_different": self.observations_different,
            "finite_numeric_observations": self.finite_numeric_observations,
            "both_nan_observations": self.both_nan_observations,
            "nonfinite_mismatch_observations": (
                self.nonfinite_mismatch_observations
            ),
            "max_abs_difference": self.max_abs_difference,
            "exact_on_common_schema": (
                self.observations_different == 0
                and self.length_mismatch_events == 0
            ),
            "schema_presence_exact": self.presence_mismatch_events == 0,
            "first_differences": self.first_differences,
        }


@dataclass(frozen=True)
class EventPayload:
    key: EventKey
    parameters: Dict[str, Any]
    collections: Dict[str, Tuple[Any, ...]]
    vertices: Dict[str, Tuple[Tuple[Any, ...], ...]]
    collection_sizes: Dict[str, int]
    path: str
    entry: int


def regular_fingerprint(path: Path) -> Tuple[int, int, int, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"input is not a regular non-symlink file: {path}")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def sha256_stable(path: Path) -> Tuple[str, int]:
    before = regular_fingerprint(path)
    digest = hashlib.sha256()
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags)
    try:
        while True:
            block = os.read(descriptor, 4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
        opened = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = regular_fingerprint(path)
    opened_fingerprint = (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    )
    if before != after or before != opened_fingerprint:
        raise RuntimeError(f"input changed while it was hashed: {path}")
    return digest.hexdigest(), before[2]


def get_parameter(frame: Any, name: str, path: Path, entry: int) -> Any:
    try:
        return frame.get_parameter(name)
    except Exception as error:
        raise RuntimeError(
            f"missing/invalid parameter {name!r} in {path}, entry {entry}"
        ) from error


def require_collection(
    frame: Any,
    available: Set[str],
    name: str,
    path: Path,
    entry: int,
) -> Any:
    if name not in available:
        raise RuntimeError(f"missing collection {name!r} in {path}, entry {entry}")
    try:
        return frame.get(name)
    except Exception as error:
        raise RuntimeError(
            f"cannot read collection {name!r} in {path}, entry {entry}"
        ) from error


def vertex_tuple(vertex: Any, root_module: Any) -> Tuple[Any, ...]:
    position = vertex.getPosition()
    covariance = tuple(
        float(root_module.delphi_aabtag_compare_vertex_cov(vertex, index))
        for index in range(6)
    )
    return (
        int(bool(vertex.isPrimary())),
        int(vertex.getAlgorithmType()),
        float(vertex.getChi2()),
        int(vertex.getNdf()),
        float(position.x),
        float(position.y),
        float(position.z),
        *covariance,
    )


def extract_event(
    frame: Any,
    path: Path,
    entry: int,
    side: str,
    allow_left_legacy_schema: bool,
    sample: str,
    root_module: Any,
) -> EventPayload:
    parameters_available = set(frame.parameters)
    collections_available = set(frame.getAvailableCollections())
    run = int(get_parameter(frame, "sDST_EVT_runNumber", path, entry))
    event = int(get_parameter(frame, "sDST_EVT_eventNumber", path, entry))
    file_sequence = int(get_parameter(frame, "sDST_EVT_fileSeq", path, entry))
    key = (run, event, file_sequence)
    if sample == "mc" and run >= 0:
        raise RuntimeError(f"non-negative MC run for {key} in {path}, entry {entry}")
    if sample == "data" and run <= 0:
        raise RuntimeError(f"non-positive Data run for {key} in {path}, entry {entry}")

    values: Dict[str, Any] = {}
    for name in STRING_PARAMETERS:
        values[name] = str(get_parameter(frame, name, path, entry))
    for name in INTEGER_PARAMETERS:
        values[name] = int(get_parameter(frame, name, path, entry))
    for name in LEGACY_OPTIONAL_INTEGER_PARAMETERS:
        if name in parameters_available:
            values[name] = int(get_parameter(frame, name, path, entry))
        elif side == "left" and allow_left_legacy_schema:
            values[name] = MISSING
        else:
            raise RuntimeError(
                f"required current parameter {name!r} is absent in {path}, "
                f"entry {entry}"
            )
    for name in FLOAT_PARAMETERS:
        values[name] = float(get_parameter(frame, name, path, entry))
    for name in FLOAT_VECTOR3_PARAMETERS:
        raw = get_parameter(frame, name, path, entry)
        vector = tuple(float(item) for item in raw)
        if len(vector) != 3:
            raise RuntimeError(
                f"parameter {name!r} has length {len(vector)}, expected 3, "
                f"in {path}, entry {entry}"
            )
        values[name] = vector

    if values["sDST_BTAGCFG_Mode"] != "recalc":
        raise RuntimeError(
            f"non-recalculated mode for {key} in {path}: "
            f"{values['sDST_BTAGCFG_Mode']!r}"
        )
    if values["sDST_BTAGCFG_Recalculated"] != 1:
        raise RuntimeError(
            f"Recalculated != 1 for {key} in {path}: "
            f"{values['sDST_BTAGCFG_Recalculated']}"
        )

    collections: Dict[str, Tuple[Any, ...]] = {}
    for name in AABTAG_INTEGER_COLLECTIONS + PV_TRACK_INTEGER_COLLECTIONS:
        collection = require_collection(
            frame, collections_available, name, path, entry
        )
        collections[name] = tuple(int(item) for item in collection)
    for name in AABTAG_FLOAT_COLLECTIONS + PV_TRACK_FLOAT_COLLECTIONS:
        collection = require_collection(
            frame, collections_available, name, path, entry
        )
        collections[name] = tuple(float(item) for item in collection)

    aabtag_lengths = {
        len(collections[name])
        for name in AABTAG_INTEGER_COLLECTIONS + AABTAG_FLOAT_COLLECTIONS
    }
    if len(aabtag_lengths) != 1:
        raise RuntimeError(
            f"AABTAG track arrays are not aligned for {key} in {path}: "
            f"{sorted(aabtag_lengths)}"
        )
    expected_tracks = values["sDST_AABTAG_NTracks"]
    if aabtag_lengths != {expected_tracks}:
        raise RuntimeError(
            f"AABTAG track-array/NTracks mismatch for {key} in {path}: "
            f"arrays={sorted(aabtag_lengths)}, NTracks={expected_tracks}"
        )

    vertices: Dict[str, Tuple[Tuple[Any, ...], ...]] = {}
    for name in VERTEX_COLLECTIONS:
        collection = require_collection(
            frame, collections_available, name, path, entry
        )
        vertices[name] = tuple(
            vertex_tuple(vertex, root_module) for vertex in collection
        )

    collection_sizes: Dict[str, int] = {}
    for name in SIZE_ONLY_COLLECTIONS:
        collection = require_collection(
            frame, collections_available, name, path, entry
        )
        collection_sizes[name] = int(collection.size())

    contract_names = (
        "sDST_AABTAG_BadEventCode",
        "sDST_AABTAG_AlgorithmInvoked",
        "sDST_AABTAG_Valid",
        "sDST_AABTAG_NTracksRaw",
    )
    if all(values[name] is not MISSING for name in contract_names):
        bad_event_code = values["sDST_AABTAG_BadEventCode"]
        algorithm_invoked = values["sDST_AABTAG_AlgorithmInvoked"]
        valid = values["sDST_AABTAG_Valid"]
        beamspot_error = values["sDST_EVT_BeamSpotErrorCode"]
        n_tracks_raw = values["sDST_AABTAG_NTracksRaw"]
        n_tracks = values["sDST_AABTAG_NTracks"]
        n_attached = values["sDST_AABTAG_NTracksAttached"]
        truncated = values["sDST_AABTAG_Truncated"]

        if bad_event_code not in (0, 1, 2):
            raise RuntimeError(
                f"raw BadEventCode is outside 0..2 for {key} in {path}: "
                f"{bad_event_code}"
            )
        if algorithm_invoked not in (0, 1) or valid not in (0, 1):
            raise RuntimeError(
                f"non-boolean AABTAG validity metadata for {key} in {path}: "
                f"AlgorithmInvoked={algorithm_invoked}, Valid={valid}"
            )
        expected_invoked = int(beamspot_error == 0)
        expected_valid = int(expected_invoked == 1 and bad_event_code == 0)
        if algorithm_invoked != expected_invoked or valid != expected_valid:
            raise RuntimeError(
                f"inconsistent AABTAG validity metadata for {key} in {path}: "
                f"BeamSpotErrorCode={beamspot_error}, "
                f"BadEventCode={bad_event_code}, "
                f"AlgorithmInvoked={algorithm_invoked}, Valid={valid}"
            )
        if not 0 <= n_tracks_raw <= 100 or not 0 <= n_tracks <= 100:
            raise RuntimeError(
                f"AABTAG track count outside 0..100 for {key} in {path}: "
                f"NTracksRaw={n_tracks_raw}, NTracks={n_tracks}"
            )
        if not 0 <= n_attached <= n_tracks:
            raise RuntimeError(
                f"AABTAG attached-track count is inconsistent for {key} in "
                f"{path}: NTracksAttached={n_attached}, NTracks={n_tracks}"
            )
        expected_truncated = int(expected_valid == 1 and n_tracks_raw == 100)
        if truncated != expected_truncated:
            raise RuntimeError(
                f"AABTAG Truncated contract mismatch for {key} in {path}: "
                f"expected {expected_truncated}, got {truncated}"
            )
        if expected_invoked == 0 and n_tracks_raw != 0:
            raise RuntimeError(
                f"skipped AABTAG event has nonzero NTracksRaw for {key} in "
                f"{path}: {n_tracks_raw}"
            )
        if expected_valid == 1 and n_tracks != n_tracks_raw:
            raise RuntimeError(
                f"valid AABTAG event has NTracks != NTracksRaw for {key} in "
                f"{path}: {n_tracks} != {n_tracks_raw}"
            )
        if expected_valid == 0 and (n_tracks != 0 or n_attached != 0):
            raise RuntimeError(
                f"invalid AABTAG event exposes track payload for {key} in "
                f"{path}: NTracks={n_tracks}, NTracksAttached={n_attached}"
            )

        event_probabilities = tuple(
            item
            for name in FLOAT_VECTOR3_PARAMETERS[:3]
            for item in values[name]
        )
        thrust = (*values["sDST_AABTAG_ThrustAxis"],
                  values["sDST_AABTAG_ThrustValue"])
        if expected_valid == 0:
            if any(not math.isnan(item) for item in event_probabilities + thrust):
                raise RuntimeError(
                    f"invalid AABTAG event has finite event payload for {key} "
                    f"in {path}"
                )
        else:
            if any(
                not math.isfinite(item) or item < 0.0 or item > 1.000001
                for item in event_probabilities
            ):
                raise RuntimeError(
                    f"valid AABTAG event has invalid probability for {key} in {path}"
                )
            axis = values["sDST_AABTAG_ThrustAxis"]
            thrust_value = values["sDST_AABTAG_ThrustValue"]
            if any(
                not math.isfinite(item) or abs(item) > 1.000001 for item in axis
            ) or (
                not math.isfinite(thrust_value)
                or thrust_value < 0.0
                or thrust_value > 1.000001
            ):
                raise RuntimeError(
                    f"valid AABTAG event has invalid thrust for {key} in {path}"
                )

        expected_pv_size = expected_valid
        if len(vertices["sDST_AABTAG_PrimaryVertex"]) != expected_pv_size:
            raise RuntimeError(
                f"AABTAG PV/Valid mismatch for {key} in {path}: expected "
                f"{expected_pv_size}, got "
                f"{len(vertices['sDST_AABTAG_PrimaryVertex'])}"
            )

    return EventPayload(
        key=key,
        parameters=values,
        collections=collections,
        vertices=vertices,
        collection_sizes=collection_sizes,
        path=str(path),
        entry=entry,
    )


def load_left_file(
    path: Path,
    root_io: Any,
    root_module: Any,
    allow_left_legacy_schema: bool,
    sample: str,
) -> Tuple[Dict[EventKey, EventPayload], List[EventKey]]:
    reader = root_io.Reader(str(path))
    events: Dict[EventKey, EventPayload] = {}
    order: List[EventKey] = []
    for entry, frame in enumerate(reader.get("events")):
        payload = extract_event(
            frame,
            path,
            entry,
            "left",
            allow_left_legacy_schema,
            sample,
            root_module,
        )
        if payload.key in events:
            previous = events[payload.key]
            raise RuntimeError(
                f"duplicate left key {payload.key}: {previous.path} entry "
                f"{previous.entry} and {path} entry {entry}"
            )
        events[payload.key] = payload
        order.append(payload.key)
    if not events:
        raise RuntimeError(f"left input has no events: {path}")
    return events, order


class Comparator:
    def __init__(self, max_examples: int) -> None:
        self.max_examples = max_examples
        self.fields: Dict[str, FieldComparison] = {}
        self.joined_events = 0
        self.left_hadronic_selected = 0
        self.right_hadronic_selected = 0
        self.hadronic_selection_changed = 0
        self.left_bad_status_known = 0
        self.left_bad_status_missing = 0
        self.left_bad_status_events = 0
        self.right_bad_status_known = 0
        self.right_bad_status_missing = 0
        self.right_bad_status_events = 0
        self.bad_status_changed_comparable = 0
        self.left_invocation_known = 0
        self.left_invocation_missing = 0
        self.left_not_invoked_events = 0
        self.right_invocation_known = 0
        self.right_invocation_missing = 0
        self.right_not_invoked_events = 0
        self.invocation_changed_comparable = 0
        self.left_validity_known = 0
        self.left_validity_missing = 0
        self.left_invalid_events = 0
        self.right_validity_known = 0
        self.right_validity_missing = 0
        self.right_invalid_events = 0
        self.validity_changed_comparable = 0
        self.left_used_for_tag_rows = 0
        self.right_used_for_tag_rows = 0
        self.used_for_tag_selection_changed_rows = 0
        self.left_attached_to_pv_rows = 0
        self.right_attached_to_pv_rows = 0
        self.attached_to_pv_selection_changed_rows = 0

    def field(self, name: str) -> FieldComparison:
        if name not in self.fields:
            self.fields[name] = FieldComparison(name, self.max_examples)
        return self.fields[name]

    def compare_event(self, left: EventPayload, right: EventPayload) -> None:
        key = left.key
        if right.key != key:
            raise RuntimeError(f"internal join error: {key} != {right.key}")
        self.joined_events += 1

        for name in STRING_PARAMETERS + INTEGER_PARAMETERS:
            self.field(name).add_scalar(
                key, left.parameters[name], right.parameters[name]
            )
        for name in LEGACY_OPTIONAL_INTEGER_PARAMETERS:
            self.field(name).add_scalar(
                key, left.parameters[name], right.parameters[name]
            )
        for name in FLOAT_PARAMETERS:
            self.field(name).add_scalar(
                key, left.parameters[name], right.parameters[name]
            )

        for name in FLOAT_VECTOR3_PARAMETERS:
            components = (
                PROBABILITY_COMPONENTS
                if "Prob" in name
                else AXIS_COMPONENTS
            )
            for index, component in enumerate(components):
                self.field(f"{name}[{component}]").add_scalar(
                    key,
                    left.parameters[name][index],
                    right.parameters[name][index],
                )

        for name in (
            AABTAG_INTEGER_COLLECTIONS
            + AABTAG_FLOAT_COLLECTIONS
            + PV_TRACK_INTEGER_COLLECTIONS
            + PV_TRACK_FLOAT_COLLECTIONS
        ):
            self.field(name).add_sequence(
                key, left.collections[name], right.collections[name]
            )

        for name in VERTEX_COLLECTIONS:
            left_vertices = left.vertices[name]
            right_vertices = right.vertices[name]
            self.field(f"{name}.size").add_scalar(
                key, len(left_vertices), len(right_vertices)
            )
            for attribute_index, attribute in enumerate(VERTEX_ATTRIBUTES):
                left_values = tuple(
                    vertex[attribute_index] for vertex in left_vertices
                )
                right_values = tuple(
                    vertex[attribute_index] for vertex in right_vertices
                )
                self.field(f"{name}.{attribute}").add_sequence(
                    key, left_values, right_values
                )

        for name in SIZE_ONLY_COLLECTIONS:
            self.field(f"{name}.size").add_scalar(
                key,
                left.collection_sizes[name],
                right.collection_sizes[name],
            )

        left_hadronic = left.parameters["sDST_EVT_hadronicTagTeam4"] == 1
        right_hadronic = right.parameters["sDST_EVT_hadronicTagTeam4"] == 1
        self.left_hadronic_selected += int(left_hadronic)
        self.right_hadronic_selected += int(right_hadronic)
        self.hadronic_selection_changed += int(left_hadronic != right_hadronic)

        left_bad = left.parameters["sDST_AABTAG_BadEventCode"]
        right_bad = right.parameters["sDST_AABTAG_BadEventCode"]
        if left_bad is MISSING:
            self.left_bad_status_missing += 1
        else:
            self.left_bad_status_known += 1
            self.left_bad_status_events += int(left_bad != 0)
        if right_bad is MISSING:
            self.right_bad_status_missing += 1
        else:
            self.right_bad_status_known += 1
            self.right_bad_status_events += int(right_bad != 0)
        if left_bad is not MISSING and right_bad is not MISSING:
            self.bad_status_changed_comparable += int(
                (left_bad != 0) != (right_bad != 0)
            )

        left_invoked = left.parameters["sDST_AABTAG_AlgorithmInvoked"]
        right_invoked = right.parameters["sDST_AABTAG_AlgorithmInvoked"]
        if left_invoked is MISSING:
            self.left_invocation_missing += 1
        else:
            self.left_invocation_known += 1
            self.left_not_invoked_events += int(left_invoked == 0)
        if right_invoked is MISSING:
            self.right_invocation_missing += 1
        else:
            self.right_invocation_known += 1
            self.right_not_invoked_events += int(right_invoked == 0)
        if left_invoked is not MISSING and right_invoked is not MISSING:
            self.invocation_changed_comparable += int(
                left_invoked != right_invoked
            )

        left_valid = left.parameters["sDST_AABTAG_Valid"]
        right_valid = right.parameters["sDST_AABTAG_Valid"]
        if left_valid is MISSING:
            self.left_validity_missing += 1
        else:
            self.left_validity_known += 1
            self.left_invalid_events += int(left_valid == 0)
        if right_valid is MISSING:
            self.right_validity_missing += 1
        else:
            self.right_validity_known += 1
            self.right_invalid_events += int(right_valid == 0)
        if left_valid is not MISSING and right_valid is not MISSING:
            self.validity_changed_comparable += int(left_valid != right_valid)

        left_used = left.collections["sDST_AABTAG_Tracks_UsedForTag"]
        right_used = right.collections["sDST_AABTAG_Tracks_UsedForTag"]
        self.left_used_for_tag_rows += sum(value > 0 for value in left_used)
        self.right_used_for_tag_rows += sum(value > 0 for value in right_used)
        self.used_for_tag_selection_changed_rows += sum(
            (left_value > 0) != (right_value > 0)
            for left_value, right_value in zip(left_used, right_used)
        )

        left_attached = left.collections["sDST_AABTAG_Tracks_AttachedToPV"]
        right_attached = right.collections["sDST_AABTAG_Tracks_AttachedToPV"]
        self.left_attached_to_pv_rows += sum(left_attached)
        self.right_attached_to_pv_rows += sum(right_attached)
        self.attached_to_pv_selection_changed_rows += sum(
            (left_value != 0) != (right_value != 0)
            for left_value, right_value in zip(left_attached, right_attached)
        )

    def summary(self) -> Dict[str, Any]:
        fields = {
            name: comparison.as_dict()
            for name, comparison in sorted(self.fields.items())
        }
        changed_common_fields = [
            name
            for name, values in fields.items()
            if not values["exact_on_common_schema"]
        ]
        schema_presence_differences = [
            name
            for name, values in fields.items()
            if not values["schema_presence_exact"]
        ]
        all_common_changed_keys: Set[EventKey] = set()
        aabtag_common_changed_keys: Set[EventKey] = set()
        schema_changed_keys: Set[EventKey] = set()
        for name, field in self.fields.items():
            all_common_changed_keys.update(field.value_changed_keys)
            schema_changed_keys.update(field.presence_changed_keys)
            if name.startswith("sDST_AABTAG_"):
                aabtag_common_changed_keys.update(field.value_changed_keys)
        aabtag_changed_fields = [
            name
            for name in changed_common_fields
            if name.startswith("sDST_AABTAG_")
        ]
        return {
            "joined_events": self.joined_events,
            "exact_all_common_fields": not changed_common_fields,
            "common_value_changed_events": len(all_common_changed_keys),
            "common_fields_changed": changed_common_fields,
            "schema_presence_differences": schema_presence_differences,
            "schema_presence_changed_events": len(schema_changed_keys),
            "aabtag": {
                "exact_all_common_fields": not aabtag_changed_fields,
                "common_value_changed_events": len(aabtag_common_changed_keys),
                "common_fields_changed": aabtag_changed_fields,
                "legacy_schema_only_fields": [
                    name
                    for name in schema_presence_differences
                    if name.startswith("sDST_AABTAG_")
                ],
            },
            "selection": {
                "hadronicTagTeam4": {
                    "left_selected": self.left_hadronic_selected,
                    "right_selected": self.right_hadronic_selected,
                    "membership_changed": self.hadronic_selection_changed,
                },
                "BadEventCode": {
                    "left_known_events": self.left_bad_status_known,
                    "left_missing_legacy_events": self.left_bad_status_missing,
                    "left_raw_nonzero_snapshots": self.left_bad_status_events,
                    "right_known_events": self.right_bad_status_known,
                    "right_missing_events": self.right_bad_status_missing,
                    "right_raw_nonzero_snapshots": self.right_bad_status_events,
                    "raw_nonzero_class_changed_on_comparable_events": (
                        self.bad_status_changed_comparable
                    ),
                    "interpretation": (
                        "Raw IBAD is current-event status only when "
                        "AlgorithmInvoked is one"
                    ),
                },
                "AlgorithmInvoked": {
                    "left_known_events": self.left_invocation_known,
                    "left_missing_legacy_events": self.left_invocation_missing,
                    "left_not_invoked_events": self.left_not_invoked_events,
                    "right_known_events": self.right_invocation_known,
                    "right_missing_events": self.right_invocation_missing,
                    "right_not_invoked_events": self.right_not_invoked_events,
                    "changed_on_comparable_events": (
                        self.invocation_changed_comparable
                    ),
                },
                "Valid": {
                    "left_known_events": self.left_validity_known,
                    "left_missing_legacy_events": self.left_validity_missing,
                    "left_invalid_events": self.left_invalid_events,
                    "right_known_events": self.right_validity_known,
                    "right_missing_events": self.right_validity_missing,
                    "right_invalid_events": self.right_invalid_events,
                    "changed_on_comparable_events": (
                        self.validity_changed_comparable
                    ),
                },
                "Tracks_UsedForTag": {
                    "left_selected_rows": self.left_used_for_tag_rows,
                    "right_selected_rows": self.right_used_for_tag_rows,
                    "selection_changed_common_rows": (
                        self.used_for_tag_selection_changed_rows
                    ),
                },
                "Tracks_AttachedToPV": {
                    "left_attached_rows": self.left_attached_to_pv_rows,
                    "right_attached_rows": self.right_attached_to_pv_rows,
                    "selection_changed_common_rows": (
                        self.attached_to_pv_selection_changed_rows
                    ),
                },
            },
            "fields": fields,
        }


def discover_pairs(
    left: Path, right: Path, patterns: Sequence[str]
) -> List[Tuple[Path, Path]]:
    left_info = left.lstat()
    right_info = right.lstat()
    if stat.S_ISREG(left_info.st_mode) and stat.S_ISREG(right_info.st_mode):
        return [(left, right)]
    if not stat.S_ISDIR(left_info.st_mode) or not stat.S_ISDIR(right_info.st_mode):
        raise RuntimeError("LEFT and RIGHT must both be regular files or directories")

    def discover(directory: Path) -> Dict[str, Path]:
        found: Dict[str, Path] = {}
        for pattern in patterns:
            for path in sorted(directory.glob(pattern)):
                regular_fingerprint(path)
                if path.name in found and found[path.name] != path:
                    raise RuntimeError(
                        f"duplicate basename selected by patterns: {path.name}"
                    )
                found[path.name] = path
        return found

    left_files = discover(left)
    right_files = discover(right)
    if not left_files or not right_files:
        raise RuntimeError("file selection is empty")
    if set(left_files) != set(right_files):
        raise RuntimeError(
            "paired basename sets differ: "
            f"left_only={sorted(set(left_files) - set(right_files))}, "
            f"right_only={sorted(set(right_files) - set(left_files))}"
        )
    return [(left_files[name], right_files[name]) for name in sorted(left_files)]


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    rendered = json.dumps(
        payload, indent=2, sort_keys=True, allow_nan=False
    ) + "\n"
    atomic_write_report_text(path, rendered)


def initialize_runtime() -> Tuple[Any, Any]:
    try:
        import ROOT
        from podio import root_io
    except ImportError as error:
        raise RuntimeError(
            "ROOT/podio are unavailable; source the Key4hep environment first"
        ) from error
    ROOT.gROOT.SetBatch(True)
    declared = ROOT.gInterpreter.Declare(
        """
#include <edm4hep/Vertex.h>
float delphi_aabtag_compare_vertex_cov(const edm4hep::Vertex& vertex,
                                       unsigned index) {
  return vertex.getCovMatrix()[index];
}
"""
    )
    if not declared:
        raise RuntimeError("could not declare the EDM4hep vertex helper")
    return ROOT, root_io


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path, help="older file or directory")
    parser.add_argument("right", type=Path, help="newer file or directory")
    parser.add_argument(
        "--glob",
        action="append",
        dest="patterns",
        help="directory selection pattern; repeatable (default: *.edm4hep.root)",
    )
    parser.add_argument("--output", type=Path, help="atomic JSON output")
    parser.add_argument(
        "--sample", choices=("mc", "data", "any"), default="any"
    )
    parser.add_argument(
        "--allow-left-legacy-schema",
        action="store_true",
        help=(
            "permit missing left-side BadEventCode, AlgorithmInvoked, Valid, "
            "and NTracksRaw only"
        ),
    )
    parser.add_argument(
        "--require-exact",
        action="store_true",
        help="return failure when any common-field value differs",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=10,
        help="first differences retained per field (default: 10)",
    )
    args = parser.parse_args(argv)
    if args.max_examples < 0:
        parser.error("--max-examples must be non-negative")

    raw_left = lexical_absolute(args.left)
    raw_right = lexical_absolute(args.right)
    patterns = args.patterns or ["*.edm4hep.root"]
    output: Path | None = None
    if args.output is not None:
        try:
            output = validate_report_destination(
                lexical_absolute(args.output),
                protected_files=(raw_left, raw_right, Path(__file__).resolve()),
                root_policies=((raw_left, ()), (raw_right, ())),
            )
        except ReportDestinationError as error:
            print(f"FAIL unsafe output destination: {error}", file=sys.stderr)
            return 2

    left = Path(os.path.realpath(raw_left))
    right = Path(os.path.realpath(raw_right))

    try:
        pairs = discover_pairs(left, right, patterns)
        if output is not None:
            output = validate_report_destination(
                output,
                protected_files=(
                    Path(__file__).resolve(),
                    *(path for pair in pairs for path in pair),
                ),
                root_policies=((left, ()), (right, ())),
            )
        root_module, root_io = initialize_runtime()
        comparator = Comparator(args.max_examples)
        global_left_keys: Set[EventKey] = set()
        global_right_keys: Set[EventKey] = set()
        file_reports: List[Dict[str, Any]] = []

        for left_path, right_path in pairs:
            left_sha, left_size = sha256_stable(left_path)
            right_sha, right_size = sha256_stable(right_path)
            left_fingerprint = regular_fingerprint(left_path)
            right_fingerprint = regular_fingerprint(right_path)
            left_events, left_order = load_left_file(
                left_path,
                root_io,
                root_module,
                args.allow_left_legacy_schema,
                args.sample,
            )
            duplicate_left_campaign = sorted(set(left_events) & global_left_keys)
            if duplicate_left_campaign:
                raise RuntimeError(
                    "left event keys recur across file pairs; first: "
                    f"{duplicate_left_campaign[:10]}"
                )
            global_left_keys.update(left_events)

            right_reader = root_io.Reader(str(right_path))
            right_order: List[EventKey] = []
            right_seen: Set[EventKey] = set()
            for entry, frame in enumerate(right_reader.get("events")):
                payload = extract_event(
                    frame,
                    right_path,
                    entry,
                    "right",
                    args.allow_left_legacy_schema,
                    args.sample,
                    root_module,
                )
                if payload.key in right_seen:
                    raise RuntimeError(
                        f"duplicate right key {payload.key} in {right_path}"
                    )
                if payload.key in global_right_keys:
                    raise RuntimeError(
                        f"right event key recurs across file pairs: {payload.key}"
                    )
                right_seen.add(payload.key)
                global_right_keys.add(payload.key)
                right_order.append(payload.key)
                if payload.key not in left_events:
                    raise RuntimeError(
                        f"right-only event key {payload.key} in {right_path}"
                    )
                comparator.compare_event(left_events[payload.key], payload)

            left_only = sorted(set(left_events) - right_seen)
            if left_only:
                raise RuntimeError(
                    f"{len(left_only)} left-only event keys for pair "
                    f"{left_path.name}; first: {left_only[:10]}"
                )
            if regular_fingerprint(left_path) != left_fingerprint:
                raise RuntimeError(f"left input changed while compared: {left_path}")
            if regular_fingerprint(right_path) != right_fingerprint:
                raise RuntimeError(f"right input changed while compared: {right_path}")
            file_reports.append(
                {
                    "basename": left_path.name,
                    "left": {
                        "path": str(left_path),
                        "size_bytes": left_size,
                        "sha256": left_sha,
                        "entries": len(left_events),
                    },
                    "right": {
                        "path": str(right_path),
                        "size_bytes": right_size,
                        "sha256": right_sha,
                        "entries": len(right_seen),
                    },
                    "joined_events": len(right_seen),
                    "entry_order_identical": left_order == right_order,
                    "exact_key_sets_identical": True,
                }
            )

        comparison = comparator.summary()
        exact_requirement_failed = (
            args.require_exact and not comparison["exact_all_common_fields"]
        )
        result_status = "FAIL" if exact_requirement_failed else "PASS"
        result: Dict[str, Any] = {
            "status": result_status,
            "format": "delphi-aabtag-recalc-comparison-v1",
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "mapping": {
                "event_key": [
                    "sDST_EVT_runNumber",
                    "sDST_EVT_eventNumber",
                    "sDST_EVT_fileSeq",
                ],
                "pairing": "basename pair, then exact event-key lookup",
                "entry_order_used_for_join": False,
                "float_exactness": "numeric exact; paired NaN sentinels compare equal",
                "max_difference": "maximum absolute difference over finite pairs",
            },
            "configuration": {
                "left": str(left),
                "right": str(right),
                "patterns": patterns,
                "sample": args.sample,
                "allow_left_legacy_schema": args.allow_left_legacy_schema,
                "require_exact": args.require_exact,
            },
            "files": file_reports,
            "comparison": comparison,
        }
        rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
        if output is not None:
            atomic_write_json(output, result)
            print(
                f"{result_status} joined={comparison['joined_events']} "
                f"common_exact={int(comparison['exact_all_common_fields'])} "
                f"changed_fields={len(comparison['common_fields_changed'])} "
                f"output={output}"
            )
        else:
            print(rendered)
        return 1 if exact_requirement_failed else 0
    except Exception as error:
        failure = {
            "status": "FAIL",
            "format": "delphi-aabtag-recalc-comparison-v1",
            "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "error": str(error),
        }
        if output is not None:
            try:
                atomic_write_json(output, failure)
            except (OSError, ReportDestinationError) as write_error:
                print(
                    f"FAIL error={error}; could not write failure report: "
                    f"{write_error}",
                    file=sys.stderr,
                )
                return 2
            print(f"FAIL error={error} output={output}", file=sys.stderr)
        else:
            print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
