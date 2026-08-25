from __future__ import annotations

from typing import Mapping


_EVIDENCE_FIELDS = {
    "healthy": (
        "thermal_peer_spread_c_last",
        "cell_imbalance_v_last",
        "coolant_peer_residual_c_last",
        "pump_current_per_1k_rpm_last",
    ),
    "coolant_pump": (
        "pump_current_per_1k_rpm_last",
        "pump_rpm_per_amp_last",
        "coolant_ambient_delta_c_last",
        "battery_ambient_delta_c_last",
    ),
    "battery_pack": (
        "cell_imbalance_v_last",
        "cell_imbalance_v_slope_per_1k_mi",
        "battery_ambient_delta_c_last",
        "pack_voltage_v_last",
    ),
    "inverter": (
        "inverter_ambient_delta_c_last",
        "corr_abs_pack_current_inverter_temp",
        "motor_inverter_delta_c_last",
        "coolant_ambient_delta_c_last",
    ),
    "traction_motor": (
        "motor_ambient_delta_c_last",
        "corr_abs_pack_current_motor_temp",
        "motor_inverter_delta_c_last",
        "pack_current_a_last",
    ),
    "coolant_temp_sensor": (
        "coolant_peer_residual_c_last",
        "thermal_peer_spread_c_last",
        "coolant_ambient_delta_c_last",
        "pump_current_per_1k_rpm_last",
    ),
}

_LABELS = {
    "thermal_peer_spread_c_last": ("Thermal peer spread", "C"),
    "cell_imbalance_v_last": ("Cell imbalance", "V"),
    "coolant_peer_residual_c_last": ("Coolant vs peer residual", "C"),
    "pump_current_per_1k_rpm_last": ("Pump current per 1k RPM", "A/1kRPM"),
    "pump_rpm_per_amp_last": ("Pump mechanical output per amp", "RPM/A"),
    "coolant_ambient_delta_c_last": ("Coolant rise above ambient", "C"),
    "battery_ambient_delta_c_last": ("Battery rise above ambient", "C"),
    "cell_imbalance_v_slope_per_1k_mi": ("Cell imbalance trend", "V/1kmi"),
    "pack_voltage_v_last": ("Pack voltage", "V"),
    "inverter_ambient_delta_c_last": ("Inverter rise above ambient", "C"),
    "corr_abs_pack_current_inverter_temp": ("Load/inverter temperature correlation", None),
    "motor_inverter_delta_c_last": ("Motor minus inverter temperature", "C"),
    "motor_ambient_delta_c_last": ("Motor rise above ambient", "C"),
    "corr_abs_pack_current_motor_temp": ("Load/motor temperature correlation", None),
    "pack_current_a_last": ("Pack current", "A"),
}


def observable_evidence(
    diagnostic_class: str,
    features: Mapping[str, float],
) -> list[dict]:
    """Return only observable engineered signals supporting UI explanation.

    The function never accepts or emits simulator-private failure truth.
    Values are context for the ranked hypothesis; they are not causal proof.
    """

    fields = _EVIDENCE_FIELDS.get(diagnostic_class, ())
    result: list[dict] = []

    for field in fields:
        if field not in features:
            continue

        label, unit = _LABELS.get(field, (field, None))
        result.append(
            {
                "feature": field,
                "label": label,
                "value": round(float(features[field]), 6),
                "unit": unit,
            }
        )

    return result
