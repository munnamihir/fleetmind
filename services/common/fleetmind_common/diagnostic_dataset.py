from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .diagnostics import (
    DiagnosticTelemetryPoint,
    assert_observable_only_features,
    diagnostic_feature_schema_hash,
    extract_diagnostic_features,
)


DIAGNOSTIC_DATASET_VERSION = "fm-diagnostics-dataset-6.3-v1"

DIAGNOSTIC_CLASSES: Tuple[str, ...] = (
    "healthy",
    "coolant_pump",
    "battery_pack",
    "inverter",
    "traction_motor",
    "coolant_temp_sensor",
)

COMPONENT_TO_CLASS = {
    "coolant_pump": "coolant_pump",
    "battery_pack": "battery_pack",
    "inverter": "inverter",
    "traction_motor": "traction_motor",
    "coolant_temp_sensor": "coolant_temp_sensor",
}

DEFAULT_DIAGNOSTIC_HORIZON_MILES = 2500.0
DEFAULT_DIAGNOSTIC_WINDOW_SIZE = 12
DEFAULT_DIAGNOSTIC_STRIDE = 4
DEFAULT_MAX_EXAMPLES_PER_VEHICLE = 32

# Frozen benchmark qualification. These gates are defined before benchmark
# results are inspected and must not be lowered to force a green status.
MIN_BENCHMARK_EXAMPLES = 1000
MIN_BENCHMARK_EXAMPLES_PER_CLASS = 20
MIN_BENCHMARK_VEHICLES_PER_CLASS = 4


@dataclass(frozen=True)
class DiagnosticFailureTruth:
    vehicle_id: str
    experiment_id: str
    component: str
    failure_mileage: float
    occurred_at: datetime


@dataclass(frozen=True)
class DiagnosticExample:
    vehicle_id: str
    experiment_id: str
    anchor_timestamp: datetime
    anchor_mileage: float
    label: str
    features: Dict[str, float]
    miles_to_failure: Optional[float]


@dataclass(frozen=True)
class DiagnosticDatasetSplit:
    train: List[DiagnosticExample]
    validation: List[DiagnosticExample]
    benchmark: List[DiagnosticExample]
    benchmark_fraction: float
    validation_fraction: float


@dataclass(frozen=True)
class DiagnosticQualification:
    status: str
    reasons: Tuple[str, ...]
    examples: int
    vehicles: int
    examples_by_class: Dict[str, int]
    vehicles_by_class: Dict[str, int]


def _stable_fraction(value: str, seed: str) -> float:
    digest = hashlib.sha256(f"{seed}:{value}".encode("utf-8")).digest()
    integer = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return integer / float(2**64)


def diagnostic_benchmark_member(
    vehicle_id: str,
    *,
    fraction: float = 0.20,
    seed: str = "fleetmind-diagnostics-benchmark-v1",
) -> bool:
    if not 0.0 < fraction < 1.0:
        raise ValueError("fraction must be between 0 and 1")
    return _stable_fraction(vehicle_id, seed) < fraction


def _development_validation_member(
    vehicle_id: str,
    label_hint: str,
    *,
    fraction: float,
    seed: str,
) -> bool:
    # Development validation may use class-aware stratification because it is
    # not the frozen benchmark. Benchmark membership above remains completely
    # label-agnostic.
    return _stable_fraction(
        f"{label_hint}:{vehicle_id}",
        seed,
    ) < fraction


def _vehicle_label_hint(examples: Sequence[DiagnosticExample]) -> str:
    fault_labels = sorted(
        {
            example.label
            for example in examples
            if example.label != "healthy"
        }
    )
    if fault_labels:
        return fault_labels[0]
    return "healthy"


def _select_failure(
    failures: Sequence[DiagnosticFailureTruth],
    vehicle_id: str,
    experiment_id: str,
) -> Optional[DiagnosticFailureTruth]:
    matches = [
        failure
        for failure in failures
        if failure.vehicle_id == vehicle_id
        and failure.experiment_id == experiment_id
    ]
    if not matches:
        return None

    # Phase 6.1 currently guarantees at most one primary fault per vehicle per
    # experiment. Fail closed if that invariant is violated.
    components = {failure.component for failure in matches}
    if len(components) > 1:
        raise ValueError(
            f"Multiple failure components for {experiment_id}/{vehicle_id}: "
            f"{sorted(components)}"
        )

    return min(matches, key=lambda failure: failure.occurred_at)


def _label_for_anchor(
    *,
    anchor_mileage: float,
    max_observed_mileage: float,
    failure: Optional[DiagnosticFailureTruth],
    horizon_miles: float,
) -> Tuple[Optional[str], Optional[float]]:
    if failure is not None:
        diagnostic_class = COMPONENT_TO_CLASS.get(failure.component)
        if diagnostic_class is None:
            raise ValueError(
                f"Unsupported diagnostic component: {failure.component}"
            )

        miles_to_failure = failure.failure_mileage - anchor_mileage

        # Never train on post-failure windows.
        if miles_to_failure < 0.0:
            return None, None

        if miles_to_failure <= horizon_miles:
            return diagnostic_class, float(miles_to_failure)

    # Healthy means "no confirmed component failure in the next horizon", not
    # "no failure event currently known". Require enough future observation to
    # prove the negative; otherwise this window is right-censored.
    if max_observed_mileage - anchor_mileage >= horizon_miles:
        return "healthy", None

    return None, None


def build_diagnostic_examples(
    telemetry_by_vehicle: Mapping[str, Sequence[DiagnosticTelemetryPoint]],
    failures: Sequence[DiagnosticFailureTruth],
    *,
    experiment_id: str,
    horizon_miles: float = DEFAULT_DIAGNOSTIC_HORIZON_MILES,
    window_size: int = DEFAULT_DIAGNOSTIC_WINDOW_SIZE,
    stride: int = DEFAULT_DIAGNOSTIC_STRIDE,
    max_examples_per_vehicle: int = DEFAULT_MAX_EXAMPLES_PER_VEHICLE,
) -> List[DiagnosticExample]:
    if not experiment_id:
        raise ValueError("experiment_id is required")
    if horizon_miles <= 0:
        raise ValueError("horizon_miles must be positive")
    if window_size < 4:
        raise ValueError("window_size must be at least 4")
    if stride < 1:
        raise ValueError("stride must be at least 1")
    if max_examples_per_vehicle < 1:
        raise ValueError("max_examples_per_vehicle must be positive")

    examples: List[DiagnosticExample] = []

    for vehicle_id, raw_points in sorted(telemetry_by_vehicle.items()):
        points = sorted(
            [
                point
                for point in raw_points
                if point.experiment_id == experiment_id
            ],
            key=lambda point: point.timestamp,
        )
        if len(points) < window_size:
            continue

        failure = _select_failure(
            failures,
            vehicle_id,
            experiment_id,
        )
        max_observed_mileage = max(point.mileage for point in points)

        vehicle_examples: List[DiagnosticExample] = []

        for end_index in range(window_size - 1, len(points), stride):
            start_index = end_index - window_size + 1
            window = points[start_index : end_index + 1]
            anchor = window[-1]

            label, miles_to_failure = _label_for_anchor(
                anchor_mileage=anchor.mileage,
                max_observed_mileage=max_observed_mileage,
                failure=failure,
                horizon_miles=horizon_miles,
            )
            if label is None:
                continue

            features = extract_diagnostic_features(window)
            assert_observable_only_features(features)

            vehicle_examples.append(
                DiagnosticExample(
                    vehicle_id=vehicle_id,
                    experiment_id=experiment_id,
                    anchor_timestamp=anchor.timestamp,
                    anchor_mileage=float(anchor.mileage),
                    label=label,
                    features=dict(features),
                    miles_to_failure=miles_to_failure,
                )
            )

        if len(vehicle_examples) > max_examples_per_vehicle:
            # Keep the latest eligible windows. This caps dominance by long-run
            # vehicles while retaining the most operationally relevant evidence.
            vehicle_examples = vehicle_examples[-max_examples_per_vehicle:]

        examples.extend(vehicle_examples)

    return examples


def split_diagnostic_examples(
    examples: Sequence[DiagnosticExample],
    *,
    benchmark_fraction: float = 0.20,
    validation_fraction: float = 0.20,
    benchmark_seed: str = "fleetmind-diagnostics-benchmark-v1",
    validation_seed: str = "fleetmind-diagnostics-validation-v1",
) -> DiagnosticDatasetSplit:
    if not 0.0 < benchmark_fraction < 1.0:
        raise ValueError("benchmark_fraction must be between 0 and 1")
    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction must be between 0 and 1")

    by_vehicle: Dict[str, List[DiagnosticExample]] = {}
    experiment_ids = {example.experiment_id for example in examples}
    if len(experiment_ids) > 1:
        raise ValueError(
            "A diagnostic split cannot mix experiment IDs"
        )

    for example in examples:
        by_vehicle.setdefault(example.vehicle_id, []).append(example)

    train: List[DiagnosticExample] = []
    validation: List[DiagnosticExample] = []
    benchmark: List[DiagnosticExample] = []

    for vehicle_id, vehicle_examples in sorted(by_vehicle.items()):
        if diagnostic_benchmark_member(
            vehicle_id,
            fraction=benchmark_fraction,
            seed=benchmark_seed,
        ):
            benchmark.extend(vehicle_examples)
            continue

        label_hint = _vehicle_label_hint(vehicle_examples)
        if _development_validation_member(
            vehicle_id,
            label_hint,
            fraction=validation_fraction,
            seed=validation_seed,
        ):
            validation.extend(vehicle_examples)
        else:
            train.extend(vehicle_examples)

    return DiagnosticDatasetSplit(
        train=train,
        validation=validation,
        benchmark=benchmark,
        benchmark_fraction=benchmark_fraction,
        validation_fraction=validation_fraction,
    )


def diagnostic_feature_schema(
    examples: Sequence[DiagnosticExample],
) -> Tuple[Tuple[str, ...], str]:
    if not examples:
        raise ValueError("At least one diagnostic example is required")

    names = tuple(sorted(examples[0].features))
    expected = set(names)

    for example in examples:
        assert_observable_only_features(example.features)
        if set(example.features) != expected:
            raise ValueError(
                "Diagnostic feature schema differs across examples"
            )

    return names, diagnostic_feature_schema_hash(examples[0].features)


def qualify_diagnostic_benchmark(
    benchmark: Sequence[DiagnosticExample],
    *,
    min_examples: int = MIN_BENCHMARK_EXAMPLES,
    min_examples_per_class: int = MIN_BENCHMARK_EXAMPLES_PER_CLASS,
    min_vehicles_per_class: int = MIN_BENCHMARK_VEHICLES_PER_CLASS,
) -> DiagnosticQualification:
    examples_by_class = {
        label: 0
        for label in DIAGNOSTIC_CLASSES
    }
    vehicles_by_class_sets = {
        label: set()
        for label in DIAGNOSTIC_CLASSES
    }

    for example in benchmark:
        if example.label not in examples_by_class:
            raise ValueError(
                f"Unexpected diagnostic label: {example.label}"
            )
        examples_by_class[example.label] += 1
        vehicles_by_class_sets[example.label].add(example.vehicle_id)

    vehicles_by_class = {
        label: len(vehicle_ids)
        for label, vehicle_ids in vehicles_by_class_sets.items()
    }

    reasons: List[str] = []

    if len(benchmark) < min_examples:
        reasons.append(
            f"benchmark examples {len(benchmark)} < required {min_examples}"
        )

    for label in DIAGNOSTIC_CLASSES:
        if examples_by_class[label] < min_examples_per_class:
            reasons.append(
                f"{label} examples {examples_by_class[label]} "
                f"< required {min_examples_per_class}"
            )
        if vehicles_by_class[label] < min_vehicles_per_class:
            reasons.append(
                f"{label} vehicles {vehicles_by_class[label]} "
                f"< required {min_vehicles_per_class}"
            )

    return DiagnosticQualification(
        status="qualified" if not reasons else "insufficient_evidence",
        reasons=tuple(reasons),
        examples=len(benchmark),
        vehicles=len({example.vehicle_id for example in benchmark}),
        examples_by_class=examples_by_class,
        vehicles_by_class=vehicles_by_class,
    )
