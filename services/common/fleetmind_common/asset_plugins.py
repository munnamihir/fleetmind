"""Shared multi-asset telemetry contracts for FleetMind Phase 9.5.

Plugins derive transparent operational attention from observable telemetry only.
They do not produce autonomous physical control or calibrated safety risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ASSET_PLUGIN_RULES_VERSION = "fm-asset-plugins-9.5-v1"


@dataclass(frozen=True)
class MetricRule:
    name: str
    warn_above: float
    critical_above: float
    unit: str


@dataclass(frozen=True)
class AssetPlugin:
    asset_type: str
    required_metrics: tuple[str, ...]
    rules: tuple[MetricRule, ...]


PLUGINS: dict[str, AssetPlugin] = {
    "robot": AssetPlugin(
        asset_type="robot",
        required_metrics=(
            "actuator_current_a",
            "actuator_temp_c",
            "actuator_torque_nm",
            "gearbox_vibration_rms",
            "gearbox_temp_c",
        ),
        rules=(
            MetricRule("actuator_current_a", 18.0, 24.0, "A"),
            MetricRule("actuator_temp_c", 72.0, 88.0, "C"),
            MetricRule("gearbox_vibration_rms", 4.5, 7.0, "mm/s"),
            MetricRule("gearbox_temp_c", 75.0, 92.0, "C"),
        ),
    ),
    "charger": AssetPlugin(
        asset_type="charger",
        required_metrics=(
            "output_kw",
            "connector_temp_c",
            "coolant_temp_c",
            "fan_current_a",
            "efficiency_pct",
            "voltage_ripple_pct",
        ),
        rules=(
            MetricRule("connector_temp_c", 62.0, 78.0, "C"),
            MetricRule("coolant_temp_c", 55.0, 68.0, "C"),
            MetricRule("fan_current_a", 4.5, 6.0, "A"),
            MetricRule("voltage_ripple_pct", 2.5, 4.0, "%"),
        ),
    ),
    "energy_system": AssetPlugin(
        asset_type="energy_system",
        required_metrics=(
            "power_kw",
            "inverter_temp_c",
            "module_imbalance_v",
            "cooling_current_a",
            "soc_pct",
        ),
        rules=(
            MetricRule("inverter_temp_c", 72.0, 88.0, "C"),
            MetricRule("module_imbalance_v", 0.08, 0.14, "V"),
            MetricRule("cooling_current_a", 6.0, 8.5, "A"),
        ),
    ),
}


def plugin_catalog() -> list[dict[str, Any]]:
    return [
        {
            "assetType": plugin.asset_type,
            "requiredMetrics": list(plugin.required_metrics),
            "rulesVersion": ASSET_PLUGIN_RULES_VERSION,
            "metricRules": [
                {
                    "metric": rule.name,
                    "warnAbove": rule.warn_above,
                    "criticalAbove": rule.critical_above,
                    "unit": rule.unit,
                }
                for rule in plugin.rules
            ],
        }
        for plugin in PLUGINS.values()
    ]


def validate_asset_event(event: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for key in ("eventId", "timestamp", "experimentId", "assetId", "assetType", "metrics"):
        if key not in event:
            errors.append(f"missing {key}")

    asset_type = str(event.get("assetType") or "")
    plugin = PLUGINS.get(asset_type)
    if plugin is None:
        errors.append(f"unsupported assetType {asset_type!r}")
        return {"valid": False, "errors": errors, "plugin": None}

    metrics = event.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("metrics must be an object")
        metrics = {}

    for metric in plugin.required_metrics:
        value = metrics.get(metric)
        if not isinstance(value, (int, float)):
            errors.append(f"metric {metric} must be numeric")

    return {
        "valid": not errors,
        "errors": errors,
        "plugin": asset_type,
        "rulesVersion": ASSET_PLUGIN_RULES_VERSION,
    }


def score_asset_event(event: dict[str, Any]) -> dict[str, Any]:
    validation = validate_asset_event(event)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))

    plugin = PLUGINS[str(event["assetType"])]
    metrics = event["metrics"]
    contributions = []
    score = 0.0

    for rule in plugin.rules:
        value = float(metrics[rule.name])
        if value >= rule.critical_above:
            contribution = 30.0
            level = "critical"
        elif value >= rule.warn_above:
            fraction = (
                (value - rule.warn_above)
                / max(1e-9, rule.critical_above - rule.warn_above)
            )
            contribution = 10.0 + min(18.0, max(0.0, fraction * 18.0))
            level = "warning"
        else:
            contribution = 0.0
            level = "normal"

        if contribution:
            score += contribution
            contributions.append(
                {
                    "metric": rule.name,
                    "value": round(value, 6),
                    "unit": rule.unit,
                    "level": level,
                    "contribution": round(contribution, 4),
                }
            )

    score = min(100.0, round(score, 4))
    if score >= 60.0:
        status = "critical"
    elif score >= 20.0:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "rulesVersion": ASSET_PLUGIN_RULES_VERSION,
        "assetType": plugin.asset_type,
        "attentionScore": score,
        "status": status,
        "evidence": contributions,
        "claimBoundary": {
            "operationalAttentionOnly": True,
            "physicalFailureProbability": False,
            "autonomousControl": False,
            "safetyDecision": False,
        },
    }
