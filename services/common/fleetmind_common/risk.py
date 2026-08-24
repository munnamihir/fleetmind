from __future__ import annotations
from dataclasses import dataclass
from math import exp


@dataclass(frozen=True)
class RiskResult:
    score: float
    status: str
    severity: str
    evidence: list[str]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))


def score_telemetry(event: dict) -> RiskResult:
    """Transparent v1 risk model.

    The first FleetMind milestone deliberately uses explainable physics-inspired
    signals. Later phases can replace/ensemble this with learned models.
    """
    pwr = event["powertrain"]
    bat = event["battery"]
    thermal = event["thermal"]

    pump_current = float(thermal["pumpCurrentA"])
    pump_rpm = float(thermal["pumpRPM"])
    coolant_temp = float(thermal["coolantTempC"])
    battery_temp = float(bat["temperatureC"])
    imbalance = float(bat["cellImbalanceV"])
    inverter_temp = float(pwr["inverterTempC"])

    evidence: list[str] = []
    linear = -4.1

    if pump_current > 3.8:
        linear += (pump_current - 3.8) * 2.8
        evidence.append(f"coolant pump current elevated ({pump_current:.2f} A)")
    if pump_rpm < 2350:
        linear += (2350 - pump_rpm) / 190
        evidence.append(f"coolant pump RPM reduced ({pump_rpm:.0f})")
    if coolant_temp > 49:
        linear += (coolant_temp - 49) * 0.16
        evidence.append(f"coolant temperature elevated ({coolant_temp:.1f} °C)")
    if battery_temp > 40:
        linear += (battery_temp - 40) * 0.18
        evidence.append(f"battery temperature elevated ({battery_temp:.1f} °C)")
    if imbalance > 0.025:
        linear += (imbalance - 0.025) * 35
        evidence.append(f"cell imbalance elevated ({imbalance:.3f} V)")
    if inverter_temp > 82:
        linear += (inverter_temp - 82) * 0.12
        evidence.append(f"inverter temperature elevated ({inverter_temp:.1f} °C)")

    score = round(_sigmoid(linear), 4)
    if score >= 0.82:
        status, severity = "critical", "critical"
    elif score >= 0.55:
        status, severity = "degraded", "warning"
    else:
        status, severity = "healthy", "info"

    return RiskResult(score=score, status=status, severity=severity, evidence=evidence)
