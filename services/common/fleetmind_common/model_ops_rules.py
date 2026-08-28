"""Model-operations compatibility and drift rules for FleetMind Phase 9.4."""

from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any


MODEL_OPS_RULES_VERSION = "fm-model-ops-9.4-v1"

MODEL_STAGES = (
    "CANDIDATE",
    "STAGING",
    "PRODUCTION",
    "ARCHIVED",
)


def distribution_stats(values: list[float]) -> dict[str, float | int | None]:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    if not clean:
        return {"count": 0, "mean": None, "std": None, "min": None, "max": None}
    return {
        "count": len(clean),
        "mean": round(mean(clean), 8),
        "std": round(pstdev(clean), 8),
        "min": round(min(clean), 8),
        "max": round(max(clean), 8),
    }


def feature_schema_compatible(
    registered_sha256: str | None,
    active_sha256: str | None,
) -> bool:
    return bool(
        registered_sha256
        and active_sha256
        and registered_sha256 == active_sha256
    )


def promotion_readiness(
    *,
    artifact_sha256: str | None,
    feature_schema_sha256: str | None,
    active_feature_schema_sha256: str | None,
    benchmark_snapshot_sha256: str | None,
    benchmark_status: str | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    if not artifact_sha256:
        reasons.append("artifact SHA-256 is missing")
    if not feature_schema_compatible(
        feature_schema_sha256,
        active_feature_schema_sha256,
    ):
        reasons.append("feature schema is incompatible with the promotion target")
    if not benchmark_snapshot_sha256:
        reasons.append("locked benchmark snapshot identity is missing")
    if str(benchmark_status or "").lower() not in ("qualified", "locked", "publishable"):
        reasons.append("benchmark evidence is not qualified")

    return {
        "rulesVersion": MODEL_OPS_RULES_VERSION,
        "ready": not reasons,
        "reasons": reasons,
        "requiresExplicitPromotion": True,
    }


def drift_report(
    baseline: dict[str, dict[str, float | int | None]],
    current: dict[str, dict[str, float | int | None]],
) -> dict[str, Any]:
    rows = []
    for feature in sorted(set(baseline) & set(current)):
        base = baseline[feature]
        now = current[feature]
        base_mean = base.get("mean")
        base_std = base.get("std")
        now_mean = now.get("mean")

        if not isinstance(base_mean, (int, float)) or not isinstance(now_mean, (int, float)):
            continue

        denominator = abs(float(base_std or 0.0))
        if denominator < 1e-9:
            denominator = max(abs(float(base_mean)) * 0.05, 1e-6)

        standardized_shift = abs(float(now_mean) - float(base_mean)) / denominator
        if standardized_shift >= 1.0:
            status = "DRIFT"
        elif standardized_shift >= 0.5:
            status = "WATCH"
        else:
            status = "STABLE"

        rows.append(
            {
                "feature": feature,
                "baselineMean": round(float(base_mean), 8),
                "currentMean": round(float(now_mean), 8),
                "baselineStd": round(float(base_std or 0.0), 8),
                "standardizedMeanShift": round(standardized_shift, 6),
                "status": status,
            }
        )

    overall = "UNKNOWN"
    if rows:
        if any(row["status"] == "DRIFT" for row in rows):
            overall = "DRIFT"
        elif any(row["status"] == "WATCH" for row in rows):
            overall = "WATCH"
        else:
            overall = "STABLE"

    return {
        "rulesVersion": MODEL_OPS_RULES_VERSION,
        "status": overall,
        "features": rows,
        "interpretation": (
            "Distribution shift monitoring is an operational compatibility signal; "
            "it is not evidence of physical degradation or model causal validity."
        ),
    }
