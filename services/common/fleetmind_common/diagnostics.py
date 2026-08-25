from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Mapping, Optional, Sequence


DIAGNOSTIC_FEATURE_SCHEMA_VERSION = "fm-diagnostics-features-6.2-v1"

# Only raw, observable vehicle sensors are summarized by the diagnostic engine.
# Hidden simulator state, FleetMind risk outputs, labels, and vehicle/context
# metadata are intentionally excluded.
DIAGNOSTIC_SENSOR_FIELDS = (
    "ambient_temp_c",
    "speed_mph",
    "soc_pct",
    "pack_voltage_v",
    "pack_current_a",
    "battery_temp_c",
    "cell_imbalance_v",
    "motor_temp_c",
    "inverter_temp_c",
    "motor_rpm",
    "coolant_temp_c",
    "pump_rpm",
    "pump_current_a",
)

FORBIDDEN_DIAGNOSTIC_FEATURES = frozenset(
    {
        # Identity / experimental provenance.
        "vehicle_id",
        "timestamp",
        "experiment_id",
        # Context deliberately excluded from the first root-cause model.
        "model",
        "factory",
        "firmware",
        "pump_revision",
        # FleetMind-derived outputs.
        "risk_score",
        "status",
        "severity",
        "alert",
        "alerts",
        # Labels / private truth.
        "failed",
        "failure",
        "failure_mileage",
        "failure_mode",
        "fault_code",
        "fault_family",
        "latent_degradation",
        "operating_profile",
        "component",
        "root_cause",
        "ground_truth",
        "occurred_at",
        "lead_miles",
    }
)

FORBIDDEN_DIAGNOSTIC_PREFIXES = (
    "failure_",
    "fault_",
    "latent_",
    "alert_",
    "ground_truth_",
    "root_cause_",
    "operating_profile_",
)


@dataclass(frozen=True)
class DiagnosticTelemetryPoint:
    timestamp: datetime
    vehicle_id: str
    experiment_id: Optional[str]
    mileage: float
    ambient_temp_c: float
    speed_mph: float
    soc_pct: float
    pack_voltage_v: float
    pack_current_a: float
    battery_temp_c: float
    cell_imbalance_v: float
    motor_temp_c: float
    inverter_temp_c: float
    motor_rpm: float
    coolant_temp_c: float
    pump_rpm: float
    pump_current_a: float


def _mean(values: Sequence[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def _std(values: Sequence[float]) -> float:
    return float(statistics.pstdev(values)) if len(values) > 1 else 0.0


def _slope_per_1000_miles(
    mileages: Sequence[float],
    values: Sequence[float],
) -> float:
    if len(mileages) < 2 or len(values) < 2:
        return 0.0

    x_mean = _mean(mileages)
    y_mean = _mean(values)
    denominator = sum((x - x_mean) ** 2 for x in mileages)

    if denominator <= 1e-12:
        return 0.0

    slope = sum(
        (x - x_mean) * (y - y_mean)
        for x, y in zip(mileages, values)
    ) / denominator
    return float(slope * 1000.0)


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0

    left_mean = _mean(left)
    right_mean = _mean(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]

    denominator = math.sqrt(
        sum(value * value for value in left_centered)
        * sum(value * value for value in right_centered)
    )
    if denominator <= 1e-12:
        return 0.0

    return float(
        sum(
            left_value * right_value
            for left_value, right_value in zip(left_centered, right_centered)
        )
        / denominator
    )


def _summarize(
    features: Dict[str, float],
    name: str,
    mileages: Sequence[float],
    values: Sequence[float],
) -> None:
    features[f"{name}_last"] = float(values[-1])
    features[f"{name}_mean"] = _mean(values)
    features[f"{name}_std"] = _std(values)
    features[f"{name}_delta"] = float(values[-1] - values[0])
    features[f"{name}_slope_per_1k_mi"] = _slope_per_1000_miles(
        mileages,
        values,
    )


def _finite(value: float, field_name: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"Non-finite telemetry value for {field_name}")
    return numeric


def validate_diagnostic_window(
    window: Sequence[DiagnosticTelemetryPoint],
) -> List[DiagnosticTelemetryPoint]:
    if len(window) < 4:
        raise ValueError(
            "At least four telemetry points are required for diagnostic features"
        )

    ordered = sorted(window, key=lambda point: point.timestamp)

    vehicle_ids = {point.vehicle_id for point in ordered}
    if len(vehicle_ids) != 1:
        raise ValueError("Diagnostic window cannot mix vehicle IDs")

    experiment_ids = {
        point.experiment_id
        for point in ordered
        if point.experiment_id is not None
    }
    if len(experiment_ids) > 1:
        raise ValueError("Diagnostic window cannot cross experiment IDs")

    previous_mileage = None
    for point in ordered:
        for field_name in ("mileage",) + DIAGNOSTIC_SENSOR_FIELDS:
            _finite(getattr(point, field_name), field_name)

        if previous_mileage is not None and point.mileage + 1e-6 < previous_mileage:
            raise ValueError(
                "Diagnostic window cannot cross a backward mileage reset"
            )
        previous_mileage = point.mileage

    return ordered


def assert_observable_only_features(features: Mapping[str, object]) -> None:
    leaked: List[str] = []

    for raw_key in features:
        key = str(raw_key).lower()

        if key in FORBIDDEN_DIAGNOSTIC_FEATURES:
            leaked.append(key)
            continue

        if any(key.startswith(prefix) for prefix in FORBIDDEN_DIAGNOSTIC_PREFIXES):
            leaked.append(key)

    if leaked:
        raise ValueError(
            "Leakage-prone diagnostic features detected: "
            f"{sorted(set(leaked))}"
        )


def diagnostic_feature_schema_hash(features: Mapping[str, object]) -> str:
    """Hash only the ordered feature names, never values or labels."""

    assert_observable_only_features(features)
    payload = "\n".join(sorted(str(key) for key in features)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def extract_diagnostic_features(
    window: Sequence[DiagnosticTelemetryPoint],
) -> Dict[str, float]:
    """Extract sensor-only root-cause features from one vehicle window.

    The output intentionally contains no vehicle ID, experiment ID, firmware,
    hardware revision, risk/status field, failure label, fault code, hidden
    simulator state, or ground-truth component.

    The engineered features are designed to distinguish competing explanations
    for similar symptoms. For example, a high reported coolant temperature can
    be compared with peer thermal sensors, pump behavior, load correlation, and
    ambient-adjusted temperature rise instead of being treated as sufficient
    evidence of a physical cooling failure by itself.
    """

    ordered = validate_diagnostic_window(window)
    mileages = [float(point.mileage) for point in ordered]

    series: Dict[str, List[float]] = {
        field_name: [
            float(getattr(point, field_name))
            for point in ordered
        ]
        for field_name in DIAGNOSTIC_SENSOR_FIELDS
    }

    features: Dict[str, float] = {
        "window_miles": max(0.0, mileages[-1] - mileages[0]),
        "samples_in_window": float(len(ordered)),
    }

    # Raw observable summaries: last value, central tendency, volatility,
    # window change, and mileage-normalized trend.
    for field_name in DIAGNOSTIC_SENSOR_FIELDS:
        _summarize(
            features,
            field_name,
            mileages,
            series[field_name],
        )

    ambient = series["ambient_temp_c"]
    battery = series["battery_temp_c"]
    motor = series["motor_temp_c"]
    inverter = series["inverter_temp_c"]
    coolant = series["coolant_temp_c"]
    pack_current = series["pack_current_a"]
    abs_pack_current = [abs(value) for value in pack_current]
    pack_voltage = series["pack_voltage_v"]
    pump_rpm = series["pump_rpm"]
    pump_current = series["pump_current_a"]

    # Ambient-adjusted thermal behavior separates environmental heat from
    # component-specific thermal divergence.
    battery_ambient = [
        battery_value - ambient_value
        for battery_value, ambient_value in zip(battery, ambient)
    ]
    motor_ambient = [
        motor_value - ambient_value
        for motor_value, ambient_value in zip(motor, ambient)
    ]
    inverter_ambient = [
        inverter_value - ambient_value
        for inverter_value, ambient_value in zip(inverter, ambient)
    ]
    coolant_ambient = [
        coolant_value - ambient_value
        for coolant_value, ambient_value in zip(coolant, ambient)
    ]

    # Cross-sensor relationships help separate a biased coolant sensor from
    # genuine system heating and distinguish motor vs inverter concentration.
    motor_inverter = [
        motor_value - inverter_value
        for motor_value, inverter_value in zip(motor, inverter)
    ]
    coolant_battery = [
        coolant_value - battery_value
        for coolant_value, battery_value in zip(coolant, battery)
    ]
    inverter_coolant = [
        inverter_value - coolant_value
        for inverter_value, coolant_value in zip(inverter, coolant)
    ]

    for name, values in (
        ("battery_ambient_delta_c", battery_ambient),
        ("motor_ambient_delta_c", motor_ambient),
        ("inverter_ambient_delta_c", inverter_ambient),
        ("coolant_ambient_delta_c", coolant_ambient),
        ("motor_inverter_delta_c", motor_inverter),
        ("coolant_battery_delta_c", coolant_battery),
        ("inverter_coolant_delta_c", inverter_coolant),
    ):
        features[f"{name}_last"] = float(values[-1])
        features[f"{name}_mean"] = _mean(values)
        features[f"{name}_slope_per_1k_mi"] = _slope_per_1000_miles(
            mileages,
            values,
        )

    # Pump electrical/mechanical relationship. A frictional pump fault can
    # consume more current while producing less RPM.
    pump_current_per_1k_rpm = [
        current / max(abs(rpm), 1.0) * 1000.0
        for current, rpm in zip(pump_current, pump_rpm)
    ]
    pump_rpm_per_amp = [
        rpm / max(abs(current), 0.05)
        for rpm, current in zip(pump_rpm, pump_current)
    ]

    _summarize(
        features,
        "pump_current_per_1k_rpm",
        mileages,
        pump_current_per_1k_rpm,
    )
    _summarize(
        features,
        "pump_rpm_per_amp",
        mileages,
        pump_rpm_per_amp,
    )

    # Load-normalized thermal rise. The denominator has a low-load floor so
    # idling samples do not explode numerically.
    load_units = [
        max(current / 100.0, 0.25)
        for current in abs_pack_current
    ]
    battery_rise_per_100a = [
        delta / load
        for delta, load in zip(battery_ambient, load_units)
    ]
    motor_rise_per_100a = [
        delta / load
        for delta, load in zip(motor_ambient, load_units)
    ]
    inverter_rise_per_100a = [
        delta / load
        for delta, load in zip(inverter_ambient, load_units)
    ]
    coolant_rise_per_100a = [
        delta / load
        for delta, load in zip(coolant_ambient, load_units)
    ]

    for name, values in (
        ("battery_temp_rise_per_100a", battery_rise_per_100a),
        ("motor_temp_rise_per_100a", motor_rise_per_100a),
        ("inverter_temp_rise_per_100a", inverter_rise_per_100a),
        ("coolant_temp_rise_per_100a", coolant_rise_per_100a),
    ):
        features[f"{name}_last"] = float(values[-1])
        features[f"{name}_mean"] = _mean(values)

    # Correlation with load distinguishes load-driven heating from readings
    # that drift independently of physical demand.
    features["corr_abs_pack_current_battery_temp"] = _pearson(
        abs_pack_current,
        battery,
    )
    features["corr_abs_pack_current_motor_temp"] = _pearson(
        abs_pack_current,
        motor,
    )
    features["corr_abs_pack_current_inverter_temp"] = _pearson(
        abs_pack_current,
        inverter,
    )
    features["corr_abs_pack_current_coolant_temp"] = _pearson(
        abs_pack_current,
        coolant,
    )
    features["corr_abs_pack_current_pack_voltage"] = _pearson(
        abs_pack_current,
        pack_voltage,
    )
    features["corr_pump_current_pump_rpm"] = _pearson(
        pump_current,
        pump_rpm,
    )

    # Thermal coherence: genuine heating usually moves multiple physical
    # sensors together, while a biased sensor can become isolated.
    peer_means = [
        _mean([battery_value, motor_value, inverter_value])
        for battery_value, motor_value, inverter_value
        in zip(battery, motor, inverter)
    ]
    coolant_peer_residual = [
        coolant_value - peer_mean
        for coolant_value, peer_mean in zip(coolant, peer_means)
    ]
    thermal_peer_spread = [
        _std(
            [
                battery_value,
                motor_value,
                inverter_value,
                coolant_value,
            ]
        )
        for battery_value, motor_value, inverter_value, coolant_value
        in zip(battery, motor, inverter, coolant)
    ]

    features["coolant_peer_residual_c_last"] = float(
        coolant_peer_residual[-1]
    )
    features["coolant_peer_residual_c_mean"] = _mean(
        coolant_peer_residual
    )
    features["coolant_peer_residual_c_slope_per_1k_mi"] = (
        _slope_per_1000_miles(mileages, coolant_peer_residual)
    )
    features["thermal_peer_spread_c_last"] = float(
        thermal_peer_spread[-1]
    )
    features["thermal_peer_spread_c_mean"] = _mean(
        thermal_peer_spread
    )

    assert_observable_only_features(features)

    for name, value in features.items():
        if not math.isfinite(float(value)):
            raise ValueError(
                f"Diagnostic feature {name} is not finite"
            )

    return features
