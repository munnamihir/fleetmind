from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence


WINDOW_NUMERIC_FIELDS = (
    "ambient_temp_c",
    "speed_mph",
    "battery_temp_c",
    "cell_imbalance_v",
    "inverter_temp_c",
    "coolant_temp_c",
    "pump_rpm",
    "pump_current_a",
)

# Deliberately forbidden from the predictive model. These fields either identify a
# vehicle, are derived by FleetMind's rule-based risk engine, or contain future truth.
FORBIDDEN_MODEL_FEATURES = frozenset(
    {
        "vehicle_id",
        "timestamp",
        "risk_score",
        "status",
        "severity",
        "alert",
        "failed",
        "failure",
        "failure_mileage",
        "failure_mode",
        "fault_code",
        "lead_miles",
        "occurred_at",
    }
)


@dataclass(frozen=True)
class TelemetryPoint:
    timestamp: datetime
    vehicle_id: str
    model: str
    factory: str
    firmware: str
    pump_revision: str
    mileage: float
    ambient_temp_c: float
    speed_mph: float
    battery_temp_c: float
    cell_imbalance_v: float
    inverter_temp_c: float
    coolant_temp_c: float
    pump_rpm: float
    pump_current_a: float


@dataclass(frozen=True)
class FailureTruth:
    vehicle_id: str
    failure_mileage: float
    occurred_at: datetime


@dataclass(frozen=True)
class FeatureExample:
    vehicle_id: str
    anchor_timestamp: datetime
    anchor_mileage: float
    label: int
    features: dict[str, float | str]
    miles_to_failure: float | None


@dataclass(frozen=True)
class DatasetSplit:
    train: list[FeatureExample]
    validation: list[FeatureExample]
    test: list[FeatureExample]
    validation_tail_fraction: float
    test_tail_fraction: float


@dataclass(frozen=True)
class FrozenBenchmarkSplit:
    """Development data plus an immutable vehicle-level benchmark cohort.

    Benchmark membership depends only on ``vehicle_id`` and a fixed seed. It is
    therefore unaffected by observed failures, labels, firmware, or model
    performance and remains stable as the simulator accumulates new evidence.
    """

    train: list[FeatureExample]
    validation: list[FeatureExample]
    benchmark: list[FeatureExample]
    benchmark_fraction: float
    validation_fraction: float
    heldout_tail_fraction: float


def _mean(values: Sequence[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def _std(values: Sequence[float]) -> float:
    return float(statistics.pstdev(values)) if len(values) > 1 else 0.0


def _slope_per_1000_miles(mileages: Sequence[float], values: Sequence[float]) -> float:
    if len(mileages) < 2 or len(values) < 2:
        return 0.0
    x_mean = _mean(mileages)
    y_mean = _mean(values)
    denom = sum((x - x_mean) ** 2 for x in mileages)
    if denom <= 1e-12:
        return 0.0
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(mileages, values)) / denom
    return float(slope * 1000.0)


def extract_window_features(window: Sequence[TelemetryPoint]) -> dict[str, float | str]:
    if len(window) < 2:
        raise ValueError("At least two telemetry points are required for a feature window")

    ordered = sorted(window, key=lambda point: point.timestamp)
    first = ordered[0]
    last = ordered[-1]
    mileages = [point.mileage for point in ordered]

    features: dict[str, float | str] = {
        "model": last.model,
        "factory": last.factory,
        "firmware": last.firmware,
        "pump_revision": last.pump_revision,
        "anchor_mileage": float(last.mileage),
        "window_miles": max(0.0, float(last.mileage - first.mileage)),
        "samples_in_window": float(len(ordered)),
    }

    for field in WINDOW_NUMERIC_FIELDS:
        values = [float(getattr(point, field)) for point in ordered]
        features[f"{field}_last"] = values[-1]
        features[f"{field}_mean"] = _mean(values)
        features[f"{field}_std"] = _std(values)
        features[f"{field}_delta"] = values[-1] - values[0]
        features[f"{field}_slope_per_1k_mi"] = _slope_per_1000_miles(mileages, values)

    rpm = max(float(last.pump_rpm), 1.0)
    features["pump_current_per_1k_rpm"] = float(last.pump_current_a) / rpm * 1000.0
    features["thermal_delta_c"] = float(last.battery_temp_c - last.ambient_temp_c)
    features["coolant_ambient_delta_c"] = float(last.coolant_temp_c - last.ambient_temp_c)

    assert_no_leakage(features)
    return features


def assert_no_leakage(features: dict[str, object]) -> None:
    lowered = {key.lower() for key in features}
    leaked: list[str] = []
    for key in lowered:
        if key in FORBIDDEN_MODEL_FEATURES:
            leaked.append(key)
            continue
        if key.startswith("failure_") or key.startswith("fault_") or key.startswith("alert_"):
            leaked.append(key)
    if leaked:
        raise ValueError(f"Leakage-prone model features detected: {sorted(leaked)}")


def latest_monotonic_segment(
    raw_points: Sequence[TelemetryPoint],
    *,
    reset_drop_miles: float = 50.0,
) -> list[TelemetryPoint]:
    """Return only the latest mileage-continuous experiment segment.

    Synthetic simulator restarts can reuse a vehicle ID while resetting its
    odometer. Windows are never allowed to cross a substantial backward mileage
    jump because doing so would mix independent experiment epochs.
    """

    if reset_drop_miles < 0:
        raise ValueError("reset_drop_miles must be non-negative")
    points = sorted(raw_points, key=lambda point: point.timestamp)
    if not points:
        return []
    segment_start = 0
    for index in range(1, len(points)):
        if points[index - 1].mileage - points[index].mileage > reset_drop_miles:
            segment_start = index
    return points[segment_start:]


def sanitize_telemetry_history(
    telemetry_by_vehicle: dict[str, Sequence[TelemetryPoint]],
    *,
    reset_drop_miles: float = 50.0,
) -> dict[str, list[TelemetryPoint]]:
    """Keep only each vehicle's latest monotonic experiment epoch."""

    return {
        vehicle_id: latest_monotonic_segment(points, reset_drop_miles=reset_drop_miles)
        for vehicle_id, points in telemetry_by_vehicle.items()
    }


def failure_applies_to_segment(
    failure: FailureTruth | None,
    points: Sequence[TelemetryPoint],
    *,
    reset_drop_miles: float = 50.0,
) -> bool:
    """Return whether failure truth belongs to the active experiment segment."""

    if failure is None or not points:
        return False
    ordered = sorted(points, key=lambda point: point.timestamp)
    first = ordered[0]
    last = ordered[-1]
    if failure.occurred_at < first.timestamp:
        return False
    if failure.failure_mileage < min(point.mileage for point in ordered) - reset_drop_miles:
        return False
    # A failure far below the current segment's mileage is evidence from an older
    # simulator epoch even if clocks were altered or replayed.
    if failure.failure_mileage < first.mileage - reset_drop_miles:
        return False
    # Future failure truth may be newer than the latest telemetry row; that is
    # valid for retrospective training as long as it belongs to this segment.
    return failure.occurred_at >= first.timestamp and last.timestamp >= first.timestamp


def build_feature_examples(
    telemetry_by_vehicle: dict[str, Sequence[TelemetryPoint]],
    failures: dict[str, FailureTruth],
    *,
    horizon_miles: float = 2500.0,
    window_size: int = 12,
    stride: int = 4,
    max_examples_per_vehicle: int = 32,
    reset_drop_miles: float = 50.0,
) -> list[FeatureExample]:
    """Build prospective feature windows with right-censoring protection.

    A positive example is anchored *before* a known failure and within
    ``horizon_miles`` of it. A negative example is used only when FleetMind can
    prove that at least ``horizon_miles`` of subsequent operation was observed
    without a failure. Windows without enough future follow-up are censored and
    excluded instead of being mislabeled as negatives.
    """

    if horizon_miles <= 0:
        raise ValueError("horizon_miles must be positive")
    if window_size < 2:
        raise ValueError("window_size must be at least 2")
    if stride < 1:
        raise ValueError("stride must be positive")

    examples: list[FeatureExample] = []

    for vehicle_id, raw_points in telemetry_by_vehicle.items():
        points = latest_monotonic_segment(raw_points, reset_drop_miles=reset_drop_miles)
        if len(points) < window_size:
            continue

        latest_mileage = max(point.mileage for point in points)
        candidate_failure = failures.get(vehicle_id)
        failure = candidate_failure if failure_applies_to_segment(candidate_failure, points, reset_drop_miles=reset_drop_miles) else None
        vehicle_examples: list[FeatureExample] = []

        for end in range(window_size - 1, len(points), stride):
            window = points[end - window_size + 1 : end + 1]
            anchor = window[-1]

            label: int
            miles_to_failure: float | None = None
            if failure is not None:
                # Failure truth must be in the future in both physical mileage and
                # wall/simulated time. This prevents old failure rows from becoming
                # labels after a simulator restart or replay.
                if failure.occurred_at <= anchor.timestamp:
                    continue
                miles_to_failure = float(failure.failure_mileage - anchor.mileage)
                if miles_to_failure <= 0:
                    continue
                label = 1 if miles_to_failure <= horizon_miles else 0
            else:
                observed_followup = float(latest_mileage - anchor.mileage)
                if observed_followup < horizon_miles:
                    # Right-censored: future outcome is not known yet.
                    continue
                label = 0

            features = extract_window_features(window)
            vehicle_examples.append(
                FeatureExample(
                    vehicle_id=vehicle_id,
                    anchor_timestamp=anchor.timestamp,
                    anchor_mileage=float(anchor.mileage),
                    label=label,
                    features=features,
                    miles_to_failure=miles_to_failure,
                )
            )

        # Keep a bounded, recent-but-spread sample per vehicle. This prevents a
        # few high-frequency vehicles from dominating the fit.
        if len(vehicle_examples) > max_examples_per_vehicle:
            step = (len(vehicle_examples) - 1) / float(max_examples_per_vehicle - 1)
            picked = []
            seen: set[int] = set()
            for idx in range(max_examples_per_vehicle):
                chosen = int(round(idx * step))
                if chosen not in seen:
                    picked.append(vehicle_examples[chosen])
                    seen.add(chosen)
            vehicle_examples = picked

        examples.extend(vehicle_examples)

    return sorted(examples, key=lambda example: example.anchor_timestamp)


def _vehicle_bucket(vehicle_id: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{vehicle_id}".encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big")
    return value / float(2**64 - 1)


def vehicle_partition(vehicle_id: str, seed: int = 20260824) -> str:
    bucket = _vehicle_bucket(vehicle_id, seed)
    if bucket < 0.70:
        return "train"
    if bucket < 0.85:
        return "validation"
    return "test"



def _stable_order(vehicle_ids: Sequence[str], seed: int) -> list[str]:
    return sorted(
        vehicle_ids,
        key=lambda vehicle_id: hashlib.sha256(f"split:{seed}:{vehicle_id}".encode("utf-8")).digest(),
    )


def _stratified_vehicle_assignments(
    by_vehicle: dict[str, Sequence[FeatureExample]],
    seed: int,
) -> dict[str, str]:
    positive_ids = [
        vehicle_id for vehicle_id, rows in by_vehicle.items() if any(row.label == 1 for row in rows)
    ]
    negative_ids = [vehicle_id for vehicle_id in by_vehicle if vehicle_id not in set(positive_ids)]
    assignments: dict[str, str] = {}

    def allocate(vehicle_ids: list[str]) -> None:
        ordered = _stable_order(vehicle_ids, seed)
        count = len(ordered)
        if count == 0:
            return
        if count == 1:
            assignments[ordered[0]] = "train"
            return
        if count == 2:
            assignments[ordered[0]] = "train"
            assignments[ordered[1]] = "validation"
            return

        validation_count = max(1, int(round(count * 0.15)))
        test_count = max(1, int(round(count * 0.15)))
        while validation_count + test_count >= count:
            if validation_count >= test_count and validation_count > 1:
                validation_count -= 1
            elif test_count > 1:
                test_count -= 1
            else:
                break
        train_count = count - validation_count - test_count

        for vehicle_id in ordered[:train_count]:
            assignments[vehicle_id] = "train"
        for vehicle_id in ordered[train_count : train_count + validation_count]:
            assignments[vehicle_id] = "validation"
        for vehicle_id in ordered[train_count + validation_count :]:
            assignments[vehicle_id] = "test"

    allocate(positive_ids)
    allocate(negative_ids)
    return assignments

def split_examples_time_and_vehicle(
    examples: Iterable[FeatureExample],
    *,
    seed: int = 20260824,
    validation_tail_fraction: float = 0.75,
    test_tail_fraction: float = 0.75,
) -> DatasetSplit:
    """Create a vehicle-isolated, late-life walk-forward evaluation split.

    Vehicle IDs are deterministically assigned to train/validation/test and can
    never cross partitions. Training uses the complete causal history of train
    vehicles. Validation and test use only the latest portion of each held-out
    vehicle's eligible windows, so evaluation is concentrated on later-life,
    forward-looking conditions where predictive maintenance matters most.

    The feature windows themselves are strictly causal and labels are based only
    on failure mileage *after* the window anchor.
    """

    rows = sorted(list(examples), key=lambda example: example.anchor_timestamp)
    if not rows:
        return DatasetSplit([], [], [], validation_tail_fraction, test_tail_fraction)
    if not (0.0 < validation_tail_fraction <= 1.0 and 0.0 < test_tail_fraction <= 1.0):
        raise ValueError("tail fractions must be in (0, 1]")

    by_vehicle: dict[str, list[FeatureExample]] = {}
    for example in rows:
        by_vehicle.setdefault(example.vehicle_id, []).append(example)

    train: list[FeatureExample] = []
    validation: list[FeatureExample] = []
    test: list[FeatureExample] = []

    assignments = _stratified_vehicle_assignments(by_vehicle, seed)

    for vehicle_id, vehicle_rows in by_vehicle.items():
        ordered = sorted(vehicle_rows, key=lambda example: example.anchor_timestamp)
        partition = assignments[vehicle_id]
        if partition == "train":
            train.extend(ordered)
        elif partition == "validation":
            keep = max(1, int(math.ceil(len(ordered) * validation_tail_fraction)))
            validation.extend(ordered[-keep:])
        else:
            keep = max(1, int(math.ceil(len(ordered) * test_tail_fraction)))
            test.extend(ordered[-keep:])

    return DatasetSplit(
        sorted(train, key=lambda example: example.anchor_timestamp),
        sorted(validation, key=lambda example: example.anchor_timestamp),
        sorted(test, key=lambda example: example.anchor_timestamp),
        validation_tail_fraction,
        test_tail_fraction,
    )



def frozen_partition(
    vehicle_id: str,
    *,
    seed: int = 20260824,
    benchmark_fraction: float = 0.20,
    validation_fraction: float = 0.15,
) -> str:
    """Return an immutable train/validation/benchmark vehicle partition.

    The assignment is intentionally label-agnostic. This prevents benchmark
    membership from changing when a previously healthy vehicle later fails.
    """

    if not (0.0 < benchmark_fraction < 1.0):
        raise ValueError("benchmark_fraction must be in (0, 1)")
    if not (0.0 < validation_fraction < 1.0 - benchmark_fraction):
        raise ValueError("validation_fraction must be positive and leave room for training")

    bucket = _vehicle_bucket(vehicle_id, seed)
    if bucket < benchmark_fraction:
        return "benchmark"
    if bucket < benchmark_fraction + validation_fraction:
        return "validation"
    return "train"


def _development_validation_ids(
    by_vehicle: dict[str, list[FeatureExample]],
    *,
    seed: int,
    benchmark_fraction: float,
    validation_fraction: float,
) -> set[str]:
    """Choose a deterministic group-stratified validation cohort.

    Benchmark membership remains purely vehicle-hash based. Within the
    development pool, validation selection is stratified by whether the vehicle
    contributes any positive causal window so calibration/threshold selection
    has outcome support when enough failures exist. All windows from a vehicle
    remain in exactly one development partition.
    """

    development_ids = [
        vehicle_id
        for vehicle_id in by_vehicle
        if frozen_partition(
            vehicle_id,
            seed=seed,
            benchmark_fraction=benchmark_fraction,
            validation_fraction=validation_fraction,
        )
        != "benchmark"
    ]
    if not development_ids:
        return set()

    development_validation_fraction = validation_fraction / (1.0 - benchmark_fraction)
    target_total = max(1, int(round(len(development_ids) * development_validation_fraction)))
    target_total = min(target_total, max(1, len(development_ids) - 1))

    positive_ids = [
        vehicle_id
        for vehicle_id in development_ids
        if any(example.label == 1 for example in by_vehicle[vehicle_id])
    ]
    negative_ids = [vehicle_id for vehicle_id in development_ids if vehicle_id not in set(positive_ids)]

    def stable(ids: list[str], salt: str) -> list[str]:
        return sorted(
            ids,
            key=lambda vehicle_id: hashlib.sha256(
                f"{salt}:{seed}:{vehicle_id}".encode("utf-8")
            ).digest(),
        )

    positive_ids = stable(positive_ids, "validation-positive")
    negative_ids = stable(negative_ids, "validation-negative")

    positive_target = 0
    if len(positive_ids) >= 2:
        positive_target = max(1, int(round(len(positive_ids) * development_validation_fraction)))
        # Preserve at least one positive vehicle for fitting.
        positive_target = min(positive_target, len(positive_ids) - 1)
    elif len(positive_ids) == 1:
        # Do not strand the only known failure vehicle in validation. The
        # trainer will correctly remain insufficient until another failure
        # vehicle exists.
        positive_target = 0

    negative_target = max(0, target_total - positive_target)
    negative_target = min(negative_target, len(negative_ids))

    chosen = set(positive_ids[:positive_target]) | set(negative_ids[:negative_target])

    # If the negative pool was too small, fill any remaining validation slots
    # from additional positive vehicles while still keeping one positive in train.
    remaining = target_total - len(chosen)
    if remaining > 0 and len(positive_ids) - positive_target > 1:
        extra_cap = max(0, len(positive_ids) - positive_target - 1)
        chosen.update(positive_ids[positive_target:positive_target + min(remaining, extra_cap)])

    return chosen


def split_examples_frozen_benchmark(
    examples: Iterable[FeatureExample],
    *,
    seed: int = 20260824,
    benchmark_fraction: float = 0.20,
    validation_fraction: float = 0.15,
    heldout_tail_fraction: float = 0.75,
) -> FrozenBenchmarkSplit:
    """Create a frozen benchmark plus outcome-supported development split.

    * Benchmark membership depends only on vehicle ID + fixed seed.
    * Train/validation remain vehicle-disjoint.
    * Development validation is deterministically group-stratified by observed
      causal outcome support so calibration does not fail merely because all
      development failures hashed into train.
    * Benchmark vehicles are never used by fit/calibration/threshold selection.

    Validation and benchmark evaluation use only the latest eligible portion of
    each held-out vehicle's causal windows, emphasizing later-life degradation.
    """

    rows = sorted(list(examples), key=lambda example: example.anchor_timestamp)
    if not rows:
        return FrozenBenchmarkSplit([], [], [], benchmark_fraction, validation_fraction, heldout_tail_fraction)
    if not (0.0 < heldout_tail_fraction <= 1.0):
        raise ValueError("heldout_tail_fraction must be in (0, 1]")

    by_vehicle: dict[str, list[FeatureExample]] = {}
    for example in rows:
        by_vehicle.setdefault(example.vehicle_id, []).append(example)

    validation_ids = _development_validation_ids(
        by_vehicle,
        seed=seed,
        benchmark_fraction=benchmark_fraction,
        validation_fraction=validation_fraction,
    )

    train: list[FeatureExample] = []
    validation: list[FeatureExample] = []
    benchmark: list[FeatureExample] = []

    for vehicle_id, vehicle_rows in by_vehicle.items():
        ordered = sorted(vehicle_rows, key=lambda example: example.anchor_timestamp)
        fixed_partition = frozen_partition(
            vehicle_id,
            seed=seed,
            benchmark_fraction=benchmark_fraction,
            validation_fraction=validation_fraction,
        )

        if fixed_partition == "benchmark":
            keep = max(1, int(math.ceil(len(ordered) * heldout_tail_fraction)))
            benchmark.extend(ordered[-keep:])
            continue

        if vehicle_id in validation_ids:
            keep = max(1, int(math.ceil(len(ordered) * heldout_tail_fraction)))
            validation.extend(ordered[-keep:])
        else:
            train.extend(ordered)

    return FrozenBenchmarkSplit(
        sorted(train, key=lambda example: example.anchor_timestamp),
        sorted(validation, key=lambda example: example.anchor_timestamp),
        sorted(benchmark, key=lambda example: example.anchor_timestamp),
        benchmark_fraction,
        validation_fraction,
        heldout_tail_fraction,
    )


def latest_feature_examples(
    telemetry_by_vehicle: dict[str, Sequence[TelemetryPoint]],
    *,
    window_size: int = 12,
    reset_drop_miles: float = 50.0,
) -> list[FeatureExample]:
    """Build one unlabeled latest feature window per vehicle for live scoring."""

    rows: list[FeatureExample] = []
    for vehicle_id, raw_points in telemetry_by_vehicle.items():
        points = latest_monotonic_segment(raw_points, reset_drop_miles=reset_drop_miles)
        if len(points) < window_size:
            continue
        window = points[-window_size:]
        anchor = window[-1]
        rows.append(
            FeatureExample(
                vehicle_id=vehicle_id,
                anchor_timestamp=anchor.timestamp,
                anchor_mileage=float(anchor.mileage),
                label=0,
                features=extract_window_features(window),
                miles_to_failure=None,
            )
        )
    return rows
