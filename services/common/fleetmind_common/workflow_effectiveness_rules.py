from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any


WORKFLOW_EFFECTIVENESS_RULES_VERSION = (
    "fm-workflow-effectiveness-7.5-v1"
)

OUTCOME_NOT_EXECUTED = "NOT_EXECUTED"
OUTCOME_TARGET_OBSERVED = "TARGET_OBSERVED"
OUTCOME_TARGET_NOT_OBSERVED = "TARGET_NOT_OBSERVED"
OUTCOME_TARGET_NOT_EVALUABLE = "TARGET_NOT_EVALUABLE"

WORKFLOW_EFFECTIVENESS_OUTCOMES = (
    OUTCOME_NOT_EXECUTED,
    OUTCOME_TARGET_OBSERVED,
    OUTCOME_TARGET_NOT_OBSERVED,
    OUTCOME_TARGET_NOT_EVALUABLE,
)

ACTION_ENSURE_REVIEW_PLAN = "ENSURE_REVIEW_PLAN"
ACTION_ENSURE_WATCHLIST = "ENSURE_WATCHLIST"


def _pct(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0

    return round(
        (float(numerator) / float(denominator)) * 100.0,
        3,
    )


def _datetime_value(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError:
            return None

    return None


def _iso(value: Any) -> str | None:
    parsed = _datetime_value(value)
    return parsed.isoformat() if parsed else None


def _hours_between(start: Any, end: Any) -> float | None:
    start_dt = _datetime_value(start)
    end_dt = _datetime_value(end)

    if start_dt is None or end_dt is None:
        return None

    seconds = (end_dt - start_dt).total_seconds()

    if seconds < 0:
        return None

    return round(seconds / 3600.0, 3)


def _median(values: list[float | None]) -> float | None:
    clean = [
        float(value)
        for value in values
        if value is not None
    ]

    if not clean:
        return None

    return round(float(median(clean)), 3)


def source_target_absent(action: dict[str, Any]) -> bool | None:
    source = action.get("sourceSnapshot") or {}
    action_type = action.get("actionType")

    if action_type == ACTION_ENSURE_REVIEW_PLAN:
        if "maintenancePlanPresent" not in source:
            return None

        return not bool(
            source.get("maintenancePlanPresent")
        )

    if action_type == ACTION_ENSURE_WATCHLIST:
        if "watchlisted" not in source:
            return None

        return not bool(source.get("watchlisted"))

    return None


def current_target_observed(
    action: dict[str, Any],
    current_record: dict[str, Any] | None,
) -> bool | None:
    if current_record is None:
        return None

    action_type = action.get("actionType")

    if action_type == ACTION_ENSURE_REVIEW_PLAN:
        return (
            current_record.get("maintenancePlanId")
            is not None
        )

    if action_type == ACTION_ENSURE_WATCHLIST:
        return bool(current_record.get("watchlisted"))

    return None


def action_effectiveness(
    action: dict[str, Any],
    current_record: dict[str, Any] | None,
) -> dict[str, Any]:
    executed = (
        action.get("status") == "EXECUTED"
        or action.get("executedAt") is not None
    )

    target_observed = current_target_observed(
        action,
        current_record,
    )

    if not executed:
        outcome = OUTCOME_NOT_EXECUTED
    elif target_observed is True:
        outcome = OUTCOME_TARGET_OBSERVED
    elif target_observed is False:
        outcome = OUTCOME_TARGET_NOT_OBSERVED
    else:
        outcome = OUTCOME_TARGET_NOT_EVALUABLE

    return {
        "actionId": action.get("actionId"),
        "policyKey": action.get("policyKey"),
        "vehicleId": action.get("vehicleId"),
        "caseId": action.get("caseId"),
        "actionType": action.get("actionType"),
        "status": action.get("status"),
        "createdAt": _iso(action.get("createdAt")),
        "approvedAt": _iso(action.get("approvedAt")),
        "rejectedAt": _iso(action.get("rejectedAt")),
        "executedAt": _iso(action.get("executedAt")),
        "hoursToApproval": _hours_between(
            action.get("createdAt"),
            action.get("approvedAt"),
        ),
        "hoursToExecution": _hours_between(
            action.get("createdAt"),
            action.get("executedAt"),
        ),
        "sourceTargetAbsent": source_target_absent(
            action
        ),
        "currentTargetObserved": target_observed,
        "outcome": outcome,
        "interpretation": (
            "Target observation describes current workflow metadata only. "
            "It does not prove that the policy caused the state, prevented "
            "a failure, improved reliability, or changed physical condition."
        ),
    }


def policy_action_effectiveness_rows(
    actions: list[dict[str, Any]],
    current_by_vehicle: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [
        action_effectiveness(
            action,
            current_by_vehicle.get(
                str(action.get("vehicleId") or "")
            ),
        )
        for action in actions
    ]

    return sorted(
        rows,
        key=lambda row: (
            str(row.get("createdAt") or ""),
            int(row.get("actionId") or 0),
        ),
    )


def summarize_policy_effectiveness(
    *,
    policy_key: str,
    actions: list[dict[str, Any]],
    current_by_vehicle: dict[str, dict[str, Any]],
    current_match_count: int = 0,
) -> dict[str, Any]:
    outcomes = policy_action_effectiveness_rows(
        actions,
        current_by_vehicle,
    )

    total = len(actions)

    pending = sum(
        1
        for action in actions
        if action.get("status") == "PENDING_APPROVAL"
    )

    approved_ready = sum(
        1
        for action in actions
        if action.get("status") == "APPROVED"
    )

    rejected = sum(
        1
        for action in actions
        if (
            action.get("status") == "REJECTED"
            or action.get("rejectedAt") is not None
        )
    )

    executed = sum(
        1
        for action in actions
        if (
            action.get("status") == "EXECUTED"
            or action.get("executedAt") is not None
        )
    )

    ever_approved = sum(
        1
        for action in actions
        if action.get("approvedAt") is not None
    )

    evaluable_executed = [
        row
        for row in outcomes
        if row["outcome"]
        in (
            OUTCOME_TARGET_OBSERVED,
            OUTCOME_TARGET_NOT_OBSERVED,
        )
    ]

    target_observed = sum(
        1
        for row in evaluable_executed
        if row["outcome"] == OUTCOME_TARGET_OBSERVED
    )

    approval_hours = [
        _hours_between(
            action.get("createdAt"),
            action.get("approvedAt"),
        )
        for action in actions
    ]

    execution_hours = [
        _hours_between(
            action.get("createdAt"),
            action.get("executedAt"),
        )
        for action in actions
    ]

    return {
        "policyKey": policy_key,
        "currentMatches": int(current_match_count),
        "materializedActions": total,
        "pendingApproval": pending,
        "approvedReady": approved_ready,
        "rejected": rejected,
        "executed": executed,
        "everApproved": ever_approved,
        "approvalRatePct": _pct(
            ever_approved,
            total,
        ),
        "executionRatePct": _pct(
            executed,
            total,
        ),
        "rejectionRatePct": _pct(
            rejected,
            total,
        ),
        "medianHoursToApproval": _median(
            approval_hours
        ),
        "medianHoursToExecution": _median(
            execution_hours
        ),
        "evaluableExecutedActions": len(
            evaluable_executed
        ),
        "executedTargetObserved": target_observed,
        "executedTargetObservationRatePct": _pct(
            target_observed,
            len(evaluable_executed),
        ),
        "interpretation": (
            "Workflow effectiveness measures policy/action lifecycle metadata "
            "and whether the intended workflow target is currently observed. "
            "It does not establish policy causality, physical repair success, "
            "failure prevention, reliability improvement, or risk reduction."
        ),
    }


def summarize_workflow_effectiveness(
    policy_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    total_actions = sum(
        int(row.get("materializedActions") or 0)
        for row in policy_summaries
    )
    pending = sum(
        int(row.get("pendingApproval") or 0)
        for row in policy_summaries
    )
    approved_ready = sum(
        int(row.get("approvedReady") or 0)
        for row in policy_summaries
    )
    rejected = sum(
        int(row.get("rejected") or 0)
        for row in policy_summaries
    )
    executed = sum(
        int(row.get("executed") or 0)
        for row in policy_summaries
    )
    ever_approved = sum(
        int(row.get("everApproved") or 0)
        for row in policy_summaries
    )

    evaluable = sum(
        int(row.get("evaluableExecutedActions") or 0)
        for row in policy_summaries
    )
    observed = sum(
        int(row.get("executedTargetObserved") or 0)
        for row in policy_summaries
    )

    return {
        "totalPolicies": len(policy_summaries),
        "currentMatches": sum(
            int(row.get("currentMatches") or 0)
            for row in policy_summaries
        ),
        "totalActions": total_actions,
        "pendingApproval": pending,
        "approvedReady": approved_ready,
        "rejected": rejected,
        "executed": executed,
        "everApproved": ever_approved,
        "approvalRatePct": _pct(
            ever_approved,
            total_actions,
        ),
        "executionRatePct": _pct(
            executed,
            total_actions,
        ),
        "rejectionRatePct": _pct(
            rejected,
            total_actions,
        ),
        "evaluableExecutedActions": evaluable,
        "executedTargetObserved": observed,
        "executedTargetObservationRatePct": _pct(
            observed,
            evaluable,
        ),
        "interpretation": (
            "Aggregate effectiveness describes workflow lifecycle throughput "
            "and current target-state observation only. It is not physical "
            "maintenance effectiveness, failure prevention, causal impact, "
            "reliability improvement, or calibrated risk reduction."
        ),
    }
