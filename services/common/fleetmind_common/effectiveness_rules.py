"""Aggregations for FleetMind Phase 8.3 closed-loop effectiveness analytics."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean, median
from typing import Any


EFFECTIVENESS_RULES_VERSION = "fm-closed-loop-effectiveness-8.3-v1"
DEFAULT_MIN_GROUP_OUTCOMES = 5


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def _distribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("status") or "UNKNOWN") for row in rows)
    return dict(sorted(counts.items()))


def _latency_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "meanHours": None, "medianHours": None, "maxHours": None}
    hours = [value / 3600.0 for value in values]
    return {
        "count": len(hours),
        "meanHours": round(mean(hours), 4),
        "medianHours": round(median(hours), 4),
        "maxHours": round(max(hours), 4),
    }


def recommendation_funnel(recommendations: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "materialized": len(recommendations),
        "assigned": sum(1 for row in recommendations if row.get("assignedAt")),
        "acknowledged": sum(1 for row in recommendations if row.get("acknowledgedAt")),
        "approvalRequired": sum(
            1 for row in recommendations if row.get("approvalRequiredAt")
        ),
        "approved": sum(1 for row in recommendations if row.get("approvedAt")),
        "executionReady": sum(
            1 for row in recommendations if row.get("executionReadyAt")
        ),
        "executed": sum(1 for row in recommendations if row.get("executedAt")),
    }


def repeated_recommendations(
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in recommendations:
        groups[
            (
                str(row.get("vehicleId") or ""),
                str(row.get("recommendationType") or ""),
            )
        ].append(row)

    repeated = [
        {
            "vehicleId": vehicle_id,
            "recommendationType": recommendation_type,
            "count": len(rows),
        }
        for (vehicle_id, recommendation_type), rows in groups.items()
        if len(rows) > 1
    ]
    repeated.sort(key=lambda row: (-row["count"], row["vehicleId"], row["recommendationType"]))
    return {
        "repeatedGroups": len(repeated),
        "recommendationsInRepeatedGroups": sum(row["count"] for row in repeated),
        "top": repeated[:25],
    }


def summarize_effectiveness(
    outcomes: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    *,
    cohort_dimension: str = "recommendationType",
    min_group_outcomes: int = DEFAULT_MIN_GROUP_OUTCOMES,
) -> dict[str, Any]:
    """Aggregate observable outcomes and workflow timing.

    Group rows below the minimum evidence gate are returned but marked withheld.
    """

    outcome_by_recommendation = {
        int(row["recommendationId"]): row
        for row in outcomes
        if row.get("recommendationId") is not None
    }

    assignment_latencies: list[float] = []
    approval_latencies: list[float] = []
    execution_latencies: list[float] = []
    observation_latencies: list[float] = []

    for rec in recommendations:
        created = rec.get("createdAt")
        assigned = rec.get("assignedAt")
        approved = rec.get("approvedAt")
        executed = rec.get("executedAt")

        for target, bucket in (
            (assigned, assignment_latencies),
            (approved, approval_latencies),
            (executed, execution_latencies),
        ):
            value = _seconds(created, target)
            if value is not None:
                bucket.append(value)

        outcome = outcome_by_recommendation.get(int(rec.get("id") or 0))
        if outcome:
            observed = outcome.get("observationCompletedAt")
            value = _seconds(executed, observed)
            if value is not None:
                observation_latencies.append(value)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        if cohort_dimension == "recommendationType":
            key = str(outcome.get("recommendationType") or "UNKNOWN")
        else:
            context = outcome.get("context") or {}
            key = str(context.get(cohort_dimension) or "UNKNOWN")
        grouped[key].append(outcome)

    groups = []
    for value, rows in sorted(grouped.items()):
        eligible = [
            row
            for row in rows
            if row.get("status")
            not in ("PENDING_OBSERVATION", "INSUFFICIENT_DATA")
        ]
        gate_met = len(eligible) >= max(1, int(min_group_outcomes))
        groups.append(
            {
                "dimension": cohort_dimension,
                "value": value,
                "outcomes": len(rows),
                "eligibleOutcomes": len(eligible),
                "evidenceGateMet": gate_met,
                "distribution": _distribution(eligible) if gate_met else {},
                "claimStatus": "descriptive_only" if gate_met else "withheld_low_evidence",
            }
        )

    coverage_closures = []
    for row in outcomes:
        baseline = row.get("baseline") or {}
        post = row.get("post") or {}
        before = baseline.get("coverageGapCount")
        after = post.get("coverageGapCount")
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            coverage_closures.append(float(before) - float(after))

    return {
        "rulesVersion": EFFECTIVENESS_RULES_VERSION,
        "recommendations": len(recommendations),
        "outcomes": len(outcomes),
        "outcomeDistribution": _distribution(outcomes),
        "funnel": recommendation_funnel(recommendations),
        "latency": {
            "assignment": _latency_summary(assignment_latencies),
            "approval": _latency_summary(approval_latencies),
            "execution": _latency_summary(execution_latencies),
            "executionToObservation": _latency_summary(observation_latencies),
        },
        "repeatedRecommendations": repeated_recommendations(recommendations),
        "coverageGapClosure": {
            "comparableOutcomes": len(coverage_closures),
            "meanGapReduction": (
                round(mean(coverage_closures), 4) if coverage_closures else None
            ),
        },
        "groups": groups,
        "evidenceGate": {
            "minimumEligibleOutcomesPerGroup": max(1, int(min_group_outcomes)),
        },
        "claimBoundary": {
            "descriptiveWorkflowAnalytics": True,
            "causalMaintenanceSuccessRate": False,
            "physicalRepairEffectiveness": False,
        },
    }
