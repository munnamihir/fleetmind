from __future__ import annotations

from copy import deepcopy
from typing import Any

FLEET_DECISION_RULES_VERSION = "fm-fleet-decision-7.0-v1"

DECISION_STATE_NOMINAL = "NOMINAL"
DECISION_STATE_OBSERVE = "OBSERVE"
DECISION_STATE_INVESTIGATE = "INVESTIGATE"
DECISION_STATE_PLAN = "PLAN"
DECISION_STATE_WORKFLOW_ACTIVE = "WORKFLOW_ACTIVE"

DECISION_STATES = (
    DECISION_STATE_NOMINAL,
    DECISION_STATE_OBSERVE,
    DECISION_STATE_INVESTIGATE,
    DECISION_STATE_PLAN,
    DECISION_STATE_WORKFLOW_ACTIVE,
)

GAP_NONHEALTHY_WITHOUT_CASE = "NONHEALTHY_WITHOUT_CASE"
GAP_UNASSIGNED_CASE = "UNASSIGNED_CASE"
GAP_PRIORITY_CASE_WITHOUT_PLAN = "PRIORITY_CASE_WITHOUT_PLAN"
GAP_DESTABILIZED_NOT_WATCHLISTED = "DESTABILIZED_NOT_WATCHLISTED"
GAP_TRAJECTORY_INELIGIBLE = "TRAJECTORY_INELIGIBLE"
GAP_PENDING_AUTOMATION_APPROVAL = "PENDING_AUTOMATION_APPROVAL"

COVERAGE_GAPS = (
    GAP_NONHEALTHY_WITHOUT_CASE,
    GAP_UNASSIGNED_CASE,
    GAP_PRIORITY_CASE_WITHOUT_PLAN,
    GAP_DESTABILIZED_NOT_WATCHLISTED,
    GAP_TRAJECTORY_INELIGIBLE,
    GAP_PENDING_AUTOMATION_APPROVAL,
)

SCENARIO_EXECUTE_PENDING_WORKFLOW_ACTIONS = "EXECUTE_PENDING_WORKFLOW_ACTIONS"
SCENARIO_ASSIGN_UNASSIGNED_CASES = "ASSIGN_UNASSIGNED_CASES"
SCENARIO_CLOSE_ALL_WORKFLOW_GAPS = "CLOSE_ALL_WORKFLOW_GAPS"

FLEET_DECISION_SCENARIOS = (
    SCENARIO_EXECUTE_PENDING_WORKFLOW_ACTIONS,
    SCENARIO_ASSIGN_UNASSIGNED_CASES,
    SCENARIO_CLOSE_ALL_WORKFLOW_GAPS,
)

COHORT_DIMENSIONS = (
    "hypothesisClass",
    "decisionState",
    "maintenanceTier",
    "reviewPriority",
    "automationStatus",
)

WORKFLOW_ACTIVE_PLAN_STATES = (
    "REVIEW",
    "PLANNED",
    "SCHEDULED",
    "DEFERRED",
    "COMPLETED",
)


def coverage_gaps(record: dict[str, Any]) -> list[str]:
    """Return deterministic workflow/evidence coverage gaps.

    Coverage gaps are operational bookkeeping signals. They are not physical
    failure labels, calibrated failure probabilities, or causal findings.
    """
    gaps: list[str] = []
    top_class = str(record.get("topClass") or "healthy")
    case_id = record.get("caseId")
    tier = record.get("maintenanceTier")
    plan_state = record.get("maintenancePlanState")
    episode_state = record.get("episodeState")

    if top_class != "healthy" and case_id is None:
        gaps.append(GAP_NONHEALTHY_WITHOUT_CASE)

    if case_id is not None and not record.get("assignedTo"):
        gaps.append(GAP_UNASSIGNED_CASE)

    if (
        case_id is not None
        and tier in ("URGENT_REVIEW", "PLAN_SERVICE")
        and not plan_state
    ):
        gaps.append(GAP_PRIORITY_CASE_WITHOUT_PLAN)

    if (
        case_id is not None
        and episode_state == "DESTABILIZED"
        and not bool(record.get("watchlisted"))
    ):
        gaps.append(GAP_DESTABILIZED_NOT_WATCHLISTED)

    if case_id is not None and record.get("trajectoryEligible") is False:
        gaps.append(GAP_TRAJECTORY_INELIGIBLE)

    if "PENDING_APPROVAL" in (record.get("automationStatuses") or []):
        gaps.append(GAP_PENDING_AUTOMATION_APPROVAL)

    return gaps


def decision_state(record: dict[str, Any]) -> str:
    """Synthesize an operational decision state, not a physical health state."""
    top_class = str(record.get("topClass") or "healthy")
    case_id = record.get("caseId")
    plan_state = record.get("maintenancePlanState")
    automation_statuses = record.get("automationStatuses") or []

    if top_class == "healthy" and case_id is None:
        return DECISION_STATE_NOMINAL

    if (
        plan_state in WORKFLOW_ACTIVE_PLAN_STATES
        or "EXECUTED" in automation_statuses
    ):
        return DECISION_STATE_WORKFLOW_ACTIVE

    if record.get("maintenanceTier") in ("URGENT_REVIEW", "PLAN_SERVICE"):
        return DECISION_STATE_PLAN

    if (
        record.get("caseStatus") in ("ACKNOWLEDGED", "INVESTIGATING")
        or record.get("reviewPriority") == "HIGH"
    ):
        return DECISION_STATE_INVESTIGATE

    return DECISION_STATE_OBSERVE


def attention_score(record: dict[str, Any], gaps: list[str]) -> float:
    """Deterministic operator-attention index.

    This is not physical failure risk, reliability probability, RUL, or a
    calibrated safety score.
    """
    score = 0.0
    if str(record.get("topClass") or "healthy") != "healthy":
        confidence = max(0.0, min(1.0, float(record.get("topConfidence") or 0.0)))
        score += confidence * 30.0

    score += {
        "HIGH": 20.0,
        "MEDIUM": 12.0,
        "LOW": 4.0,
    }.get(record.get("reviewPriority"), 0.0)

    score += {
        "URGENT_REVIEW": 25.0,
        "PLAN_SERVICE": 18.0,
        "MONITOR": 8.0,
        "ROUTINE_REVIEW": 2.0,
    }.get(record.get("maintenanceTier"), 0.0)

    score += {
        "DESTABILIZED": 10.0,
        "STABILIZED": 5.0,
        "EVOLVING": 3.0,
        "EMERGING": 2.0,
    }.get(record.get("episodeState"), 0.0)

    gap_weights = {
        GAP_NONHEALTHY_WITHOUT_CASE: 12.0,
        GAP_UNASSIGNED_CASE: 5.0,
        GAP_PRIORITY_CASE_WITHOUT_PLAN: 10.0,
        GAP_DESTABILIZED_NOT_WATCHLISTED: 8.0,
        GAP_TRAJECTORY_INELIGIBLE: 5.0,
        GAP_PENDING_AUTOMATION_APPROVAL: 4.0,
    }
    score += sum(gap_weights.get(gap, 0.0) for gap in gaps)

    if bool(record.get("watchlisted")):
        score += 2.0

    return round(min(100.0, score), 3)


def workload_units(record: dict[str, Any], state: str, gaps: list[str]) -> float:
    """Return synthetic workflow load units.

    Units are a deterministic prioritization device, not labor hours, service
    duration, physical risk, or predicted maintenance effort.
    """
    plan_state = record.get("maintenancePlanState")
    if state == DECISION_STATE_NOMINAL:
        units = 0.0
    elif state == DECISION_STATE_OBSERVE:
        units = 0.5
    elif state == DECISION_STATE_INVESTIGATE:
        units = 1.5
    elif state == DECISION_STATE_PLAN:
        units = 2.5
    else:
        units = {
            "REVIEW": 1.25,
            "PLANNED": 1.5,
            "SCHEDULED": 0.75,
            "DEFERRED": 0.75,
            "COMPLETED": 0.25,
        }.get(plan_state, 1.0)

    if GAP_UNASSIGNED_CASE in gaps:
        units += 0.5
    if GAP_TRAJECTORY_INELIGIBLE in gaps:
        units += 0.5

    pending_count = sum(
        1
        for status in (record.get("automationStatuses") or [])
        if status == "PENDING_APPROVAL"
    )
    units += min(1.0, pending_count * 0.25)

    return round(units, 2)


def derive_fleet_decision(record: dict[str, Any]) -> dict[str, Any]:
    """Attach deterministic decision-state, attention and coverage metadata."""
    result = deepcopy(record)
    gaps = coverage_gaps(result)
    state = decision_state(result)
    result["coverageGaps"] = gaps
    result["decisionState"] = state
    result["attentionScore"] = attention_score(result, gaps)
    result["workloadUnits"] = workload_units(result, state, gaps)
    return result


def summarize_fleet_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_state = {
        state: sum(1 for record in records if record.get("decisionState") == state)
        for state in DECISION_STATES
    }
    gap_counts = {
        gap: sum(1 for record in records if gap in (record.get("coverageGaps") or []))
        for gap in COVERAGE_GAPS
    }
    return {
        "totalVehicles": len(records),
        "nonHealthyHypotheses": sum(
            1 for record in records if record.get("topClass") != "healthy"
        ),
        "vehiclesWithCases": sum(
            1 for record in records if record.get("caseId") is not None
        ),
        "attentionRequired": sum(
            1
            for record in records
            if record.get("decisionState") != DECISION_STATE_NOMINAL
        ),
        "totalWorkloadUnits": round(
            sum(float(record.get("workloadUnits") or 0.0) for record in records),
            2,
        ),
        "vehiclesWithCoverageGaps": sum(
            1 for record in records if record.get("coverageGaps")
        ),
        "coverageGapInstances": sum(gap_counts.values()),
        "byDecisionState": [
            {"state": state, "vehicles": by_state[state]}
            for state in DECISION_STATES
        ],
        "byCoverageGap": [
            {"gap": gap, "vehicles": gap_counts[gap]}
            for gap in COVERAGE_GAPS
        ],
    }


def apply_workflow_scenario(
    record: dict[str, Any],
    scenario: str,
) -> dict[str, Any]:
    """Simulate workflow-state changes without predicting physical outcomes."""
    if scenario not in FLEET_DECISION_SCENARIOS:
        raise ValueError(f"Unsupported fleet decision scenario: {scenario}")

    next_record = deepcopy(record)
    pending_types = set(next_record.get("pendingActionTypes") or [])

    if scenario in (
        SCENARIO_EXECUTE_PENDING_WORKFLOW_ACTIONS,
        SCENARIO_CLOSE_ALL_WORKFLOW_GAPS,
    ):
        if (
            "ENSURE_REVIEW_PLAN" in pending_types
            and not next_record.get("maintenancePlanState")
        ):
            next_record["maintenancePlanState"] = "REVIEW"
        if "ENSURE_WATCHLIST" in pending_types:
            next_record["watchlisted"] = True

        next_record["automationStatuses"] = [
            status
            for status in (next_record.get("automationStatuses") or [])
            if status != "PENDING_APPROVAL"
        ]
        if pending_types and "EXECUTED" not in next_record["automationStatuses"]:
            next_record["automationStatuses"].append("EXECUTED")
        next_record["pendingActionTypes"] = []

    if scenario in (
        SCENARIO_ASSIGN_UNASSIGNED_CASES,
        SCENARIO_CLOSE_ALL_WORKFLOW_GAPS,
    ):
        if next_record.get("caseId") is not None and not next_record.get("assignedTo"):
            next_record["assignedTo"] = "scenario_operator"

    if scenario == SCENARIO_CLOSE_ALL_WORKFLOW_GAPS:
        if (
            next_record.get("caseId") is not None
            and next_record.get("maintenanceTier")
            in ("URGENT_REVIEW", "PLAN_SERVICE")
            and not next_record.get("maintenancePlanState")
        ):
            next_record["maintenancePlanState"] = "REVIEW"

        if (
            next_record.get("caseId") is not None
            and next_record.get("episodeState") == "DESTABILIZED"
        ):
            next_record["watchlisted"] = True

    return derive_fleet_decision(next_record)
