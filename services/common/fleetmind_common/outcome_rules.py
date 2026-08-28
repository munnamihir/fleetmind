"""Deterministic post-workflow outcome evaluation for FleetMind Phase 8.2.

The output is an observation classification. It is not proof that a workflow
caused a physical repair, prevented a failure, or changed vehicle safety.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


OUTCOME_RULES_VERSION = "fm-closed-loop-outcomes-8.2-v1"

PENDING_OBSERVATION = "PENDING_OBSERVATION"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
IMPROVED = "IMPROVED"
STABLE = "STABLE"
WORSENED = "WORSENED"
NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"

OUTCOME_STATES = (
    PENDING_OBSERVATION,
    INSUFFICIENT_DATA,
    IMPROVED,
    STABLE,
    WORSENED,
    NO_MATERIAL_CHANGE,
)

DEFAULT_MIN_OBSERVATION_MILES = 50.0
DEFAULT_MIN_OBSERVATION_SECONDS = 300.0

_TELEMETRY_STATUS_RANK = {
    "healthy": 0,
    "degraded": 1,
    "critical": 2,
}

_CASE_STATUS_RANK = {
    "CLOSED": 0,
    "RESOLVED": 0,
    "MONITORING": 1,
    "OPEN": 2,
    "INVESTIGATING": 3,
    "ESCALATED": 4,
}


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def outcome_evaluation_key(
    *,
    recommendation_id: int,
    evaluation_version: str = OUTCOME_RULES_VERSION,
) -> str:
    """Stable identity for the current evaluator version.

    Re-evaluating after more post-execution evidence updates the same outcome
    record rather than creating duplicates.
    """

    payload = {
        "recommendationId": int(recommendation_id),
        "evaluationVersion": str(evaluation_version),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _factor(
    metric: str,
    baseline: Any,
    post: Any,
    contribution: float,
    interpretation: str,
) -> dict[str, Any]:
    baseline_num = _number(baseline)
    post_num = _number(post)
    delta = (
        round(post_num - baseline_num, 6)
        if baseline_num is not None and post_num is not None
        else None
    )
    return {
        "metric": metric,
        "baseline": baseline,
        "post": post,
        "delta": delta,
        "contribution": round(float(contribution), 4),
        "interpretation": interpretation,
    }


def evaluate_observed_outcome(
    baseline: dict[str, Any] | None,
    post: dict[str, Any] | None,
    *,
    min_observation_miles: float = DEFAULT_MIN_OBSERVATION_MILES,
    min_observation_seconds: float = DEFAULT_MIN_OBSERVATION_SECONDS,
) -> dict[str, Any]:
    """Compare observable baseline/post evidence using explainable rules.

    Positive score means the observed signals moved in a direction FleetMind
    defines as improvement. Negative score means worsening. Neither direction
    is causal attribution.
    """

    if not baseline:
        return {
            "evaluationVersion": OUTCOME_RULES_VERSION,
            "status": INSUFFICIENT_DATA,
            "score": 0.0,
            "factors": [],
            "reason": "No baseline evidence is available around workflow execution.",
            "observation": {},
            "claimBoundary": _claim_boundary(),
        }

    if not post:
        return {
            "evaluationVersion": OUTCOME_RULES_VERSION,
            "status": PENDING_OBSERVATION,
            "score": 0.0,
            "factors": [],
            "reason": "No post-execution evidence has been observed yet.",
            "observation": {},
            "claimBoundary": _claim_boundary(),
        }

    baseline_mileage = _number(baseline.get("mileage"))
    post_mileage = _number(post.get("mileage"))
    mileage_delta = (
        post_mileage - baseline_mileage
        if baseline_mileage is not None and post_mileage is not None
        else None
    )

    baseline_time = _parse_time(baseline.get("timestamp"))
    post_time = _parse_time(post.get("timestamp"))
    seconds_delta = (
        (post_time - baseline_time).total_seconds()
        if baseline_time is not None and post_time is not None
        else None
    )

    enough_miles = mileage_delta is not None and mileage_delta >= min_observation_miles
    enough_time = seconds_delta is not None and seconds_delta >= min_observation_seconds
    if not enough_miles and not enough_time:
        return {
            "evaluationVersion": OUTCOME_RULES_VERSION,
            "status": INSUFFICIENT_DATA,
            "score": 0.0,
            "factors": [],
            "reason": (
                "Post-execution evidence exists, but the observation window is "
                "too small for classification."
            ),
            "observation": {
                "mileageDelta": round(mileage_delta, 3) if mileage_delta is not None else None,
                "secondsDelta": round(seconds_delta, 3) if seconds_delta is not None else None,
                "minimumMiles": float(min_observation_miles),
                "minimumSeconds": float(min_observation_seconds),
            },
            "claimBoundary": _claim_boundary(),
        }

    score = 0.0
    factors: list[dict[str, Any]] = []

    baseline_risk = _number(baseline.get("riskScore"))
    post_risk = _number(post.get("riskScore"))
    if baseline_risk is not None and post_risk is not None:
        contribution = _clamp((baseline_risk - post_risk) * 35.0, -30.0, 30.0)
        score += contribution
        factors.append(
            _factor(
                "riskScore",
                baseline_risk,
                post_risk,
                contribution,
                "Lower FleetMind anomaly score contributes toward observed improvement.",
            )
        )

    baseline_status = str(baseline.get("telemetryStatus") or "").lower()
    post_status = str(post.get("telemetryStatus") or "").lower()
    if baseline_status in _TELEMETRY_STATUS_RANK and post_status in _TELEMETRY_STATUS_RANK:
        rank_delta = (
            _TELEMETRY_STATUS_RANK[baseline_status]
            - _TELEMETRY_STATUS_RANK[post_status]
        )
        contribution = float(rank_delta * 18.0)
        score += contribution
        factors.append(
            _factor(
                "telemetryStatusRank",
                _TELEMETRY_STATUS_RANK[baseline_status],
                _TELEMETRY_STATUS_RANK[post_status],
                contribution,
                "Movement toward FleetMind's healthy telemetry state is supportive evidence.",
            )
        )

    baseline_class = str(baseline.get("topClass") or "")
    post_class = str(post.get("topClass") or "")
    baseline_confidence = _number(baseline.get("topConfidence"))
    post_confidence = _number(post.get("topConfidence"))
    if baseline_class and post_class:
        contribution = 0.0
        if baseline_class != "healthy" and post_class == "healthy":
            contribution = 22.0
        elif baseline_class == "healthy" and post_class != "healthy":
            contribution = -22.0
        elif (
            baseline_class == post_class
            and baseline_class != "healthy"
            and baseline_confidence is not None
            and post_confidence is not None
        ):
            contribution = _clamp(
                (baseline_confidence - post_confidence) * 28.0,
                -18.0,
                18.0,
            )
        if contribution != 0.0:
            score += contribution
            factors.append(
                _factor(
                    "diagnosticHypothesis",
                    {
                        "class": baseline_class,
                        "confidence": baseline_confidence,
                    },
                    {
                        "class": post_class,
                        "confidence": post_confidence,
                    },
                    contribution,
                    "Diagnostic hypothesis movement is model evidence, not failure truth.",
                )
            )

    baseline_attention = _number(baseline.get("attentionScore"))
    post_attention = _number(post.get("attentionScore"))
    if baseline_attention is not None and post_attention is not None:
        contribution = _clamp(
            (baseline_attention - post_attention) / 100.0 * 20.0,
            -15.0,
            15.0,
        )
        score += contribution
        factors.append(
            _factor(
                "attentionScore",
                baseline_attention,
                post_attention,
                contribution,
                "Lower operational attention is supportive workflow evidence, not physical risk.",
            )
        )

    baseline_gaps = _number(baseline.get("coverageGapCount"))
    post_gaps = _number(post.get("coverageGapCount"))
    if baseline_gaps is not None and post_gaps is not None:
        contribution = _clamp((baseline_gaps - post_gaps) * 4.0, -12.0, 12.0)
        score += contribution
        factors.append(
            _factor(
                "coverageGapCount",
                baseline_gaps,
                post_gaps,
                contribution,
                "Closing workflow coverage gaps contributes toward observed improvement.",
            )
        )

    baseline_case = str(baseline.get("caseStatus") or "").upper()
    post_case = str(post.get("caseStatus") or "").upper()
    if baseline_case in _CASE_STATUS_RANK and post_case in _CASE_STATUS_RANK:
        rank_delta = _CASE_STATUS_RANK[baseline_case] - _CASE_STATUS_RANK[post_case]
        contribution = float(rank_delta * 5.0)
        score += contribution
        factors.append(
            _factor(
                "caseStatusRank",
                _CASE_STATUS_RANK[baseline_case],
                _CASE_STATUS_RANK[post_case],
                contribution,
                "Case de-escalation is workflow evidence only.",
            )
        )

    if not factors:
        status = INSUFFICIENT_DATA
        reason = "No comparable supported evidence dimensions were available."
        score = 0.0
    else:
        score = round(_clamp(score, -100.0, 100.0), 4)
        if score >= 15.0:
            status = IMPROVED
        elif score <= -15.0:
            status = WORSENED
        elif -5.0 <= score <= 5.0:
            status = NO_MATERIAL_CHANGE
        else:
            status = STABLE
        reason = "Classification is derived from deterministic observable pre/post deltas."

    return {
        "evaluationVersion": OUTCOME_RULES_VERSION,
        "status": status,
        "score": score,
        "factors": factors,
        "reason": reason,
        "observation": {
            "mileageDelta": round(mileage_delta, 3) if mileage_delta is not None else None,
            "secondsDelta": round(seconds_delta, 3) if seconds_delta is not None else None,
            "minimumMiles": float(min_observation_miles),
            "minimumSeconds": float(min_observation_seconds),
        },
        "claimBoundary": _claim_boundary(),
    }


def _claim_boundary() -> dict[str, bool]:
    return {
        "observedChangeOnly": True,
        "physicalRepairConfirmed": False,
        "maintenanceCausalityEstablished": False,
        "failurePreventionEstablished": False,
        "safetyEffectEstablished": False,
    }
