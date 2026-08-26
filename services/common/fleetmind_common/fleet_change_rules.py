from __future__ import annotations

from typing import Any


FLEET_CHANGE_RULES_VERSION = "fm-fleet-change-7.3-v1"

TRANSITION_NEW_ATTENTION = "NEW_ATTENTION"
TRANSITION_RESOLVED_ATTENTION = "RESOLVED_ATTENTION"
TRANSITION_ESCALATED = "ESCALATED"
TRANSITION_DEESCALATED = "DEESCALATED"
TRANSITION_WORKFLOW_STARTED = "WORKFLOW_STARTED"
TRANSITION_WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"
TRANSITION_COVERAGE_IMPROVED = "COVERAGE_IMPROVED"
TRANSITION_COVERAGE_REGRESSED = "COVERAGE_REGRESSED"
TRANSITION_CASE_OPENED = "CASE_OPENED"
TRANSITION_CASE_CLOSED = "CASE_CLOSED"
TRANSITION_PLAN_ADDED = "PLAN_ADDED"
TRANSITION_PLAN_REMOVED = "PLAN_REMOVED"
TRANSITION_AUTOMATION_STARTED = "AUTOMATION_STARTED"
TRANSITION_AUTOMATION_EXECUTED = "AUTOMATION_EXECUTED"

FLEET_CHANGE_TRANSITIONS = (
    TRANSITION_NEW_ATTENTION,
    TRANSITION_RESOLVED_ATTENTION,
    TRANSITION_ESCALATED,
    TRANSITION_DEESCALATED,
    TRANSITION_WORKFLOW_STARTED,
    TRANSITION_WORKFLOW_COMPLETED,
    TRANSITION_COVERAGE_IMPROVED,
    TRANSITION_COVERAGE_REGRESSED,
    TRANSITION_CASE_OPENED,
    TRANSITION_CASE_CLOSED,
    TRANSITION_PLAN_ADDED,
    TRANSITION_PLAN_REMOVED,
    TRANSITION_AUTOMATION_STARTED,
    TRANSITION_AUTOMATION_EXECUTED,
)

ATTENTION_STATE_RANK = {
    "NOMINAL": 0,
    "OBSERVE": 1,
    "INVESTIGATE": 2,
    "PLAN": 3,
}

COMPARISON_FIELDS = (
    "topClass",
    "topConfidence",
    "decisionState",
    "attentionScore",
    "workloadUnits",
    "caseId",
    "caseStatus",
    "reviewPriority",
    "episodeId",
    "episodeState",
    "maintenanceTier",
    "maintenancePlanId",
    "maintenancePlanState",
    "assignedTo",
    "watchlisted",
    "trajectoryEligible",
    "automationStatuses",
    "pendingActionTypes",
    "coverageGaps",
)


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _normalized_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value)


def canonical_change_state(record: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "vehicleId": record.get("vehicleId"),
    }

    for field in COMPARISON_FIELDS:
        value = record.get(field)

        if field in (
            "automationStatuses",
            "pendingActionTypes",
            "coverageGaps",
        ):
            state[field] = _normalized_list(value)
        else:
            state[field] = value

    return state


def _attention_required(record: dict[str, Any]) -> bool:
    return str(record.get("decisionState") or "NOMINAL") != "NOMINAL"


def _transition_types(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[str]:
    transitions: list[str] = []

    before_state = str(before.get("decisionState") or "NOMINAL")
    after_state = str(after.get("decisionState") or "NOMINAL")

    before_attention = _attention_required(before)
    after_attention = _attention_required(after)

    if not before_attention and after_attention:
        transitions.append(TRANSITION_NEW_ATTENTION)

    if before_attention and not after_attention:
        transitions.append(TRANSITION_RESOLVED_ATTENTION)

    before_rank = ATTENTION_STATE_RANK.get(before_state)
    after_rank = ATTENTION_STATE_RANK.get(after_state)

    if before_rank is not None and after_rank is not None:
        if after_rank > before_rank:
            transitions.append(TRANSITION_ESCALATED)
        elif after_rank < before_rank:
            transitions.append(TRANSITION_DEESCALATED)

    if (
        before_state != "WORKFLOW_ACTIVE"
        and after_state == "WORKFLOW_ACTIVE"
    ):
        transitions.append(TRANSITION_WORKFLOW_STARTED)

    if (
        str(before.get("maintenancePlanState") or "") != "COMPLETED"
        and str(after.get("maintenancePlanState") or "") == "COMPLETED"
    ):
        transitions.append(TRANSITION_WORKFLOW_COMPLETED)

    before_gaps = _normalized_list(before.get("coverageGaps"))
    after_gaps = _normalized_list(after.get("coverageGaps"))

    if len(after_gaps) < len(before_gaps):
        transitions.append(TRANSITION_COVERAGE_IMPROVED)
    elif len(after_gaps) > len(before_gaps):
        transitions.append(TRANSITION_COVERAGE_REGRESSED)

    before_case_id = before.get("caseId")
    after_case_id = after.get("caseId")

    if before_case_id is None and after_case_id is not None:
        transitions.append(TRANSITION_CASE_OPENED)

    if (
        before_case_id is not None
        and str(before.get("caseStatus") or "") != "CLOSED"
        and str(after.get("caseStatus") or "") == "CLOSED"
    ):
        transitions.append(TRANSITION_CASE_CLOSED)

    before_plan = before.get("maintenancePlanId")
    after_plan = after.get("maintenancePlanId")

    if before_plan is None and after_plan is not None:
        transitions.append(TRANSITION_PLAN_ADDED)

    if before_plan is not None and after_plan is None:
        transitions.append(TRANSITION_PLAN_REMOVED)

    before_automation = set(
        _normalized_list(before.get("automationStatuses"))
    )
    after_automation = set(
        _normalized_list(after.get("automationStatuses"))
    )

    if not before_automation and after_automation:
        transitions.append(TRANSITION_AUTOMATION_STARTED)

    if (
        "EXECUTED" not in before_automation
        and "EXECUTED" in after_automation
    ):
        transitions.append(TRANSITION_AUTOMATION_EXECUTED)

    return transitions


def vehicle_state_change(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    before_state = canonical_change_state(before)
    after_state = canonical_change_state(after)

    changed_fields = [
        field
        for field in COMPARISON_FIELDS
        if before_state.get(field) != after_state.get(field)
    ]

    transitions = _transition_types(before_state, after_state)

    before_gaps = _normalized_list(before_state.get("coverageGaps"))
    after_gaps = _normalized_list(after_state.get("coverageGaps"))

    return {
        "vehicleId": after_state.get("vehicleId")
        or before_state.get("vehicleId"),
        "changed": bool(changed_fields),
        "changedFields": changed_fields,
        "transitions": transitions,
        "fromDecisionState": before_state.get("decisionState"),
        "toDecisionState": after_state.get("decisionState"),
        "fromAttentionScore": round(
            _safe_float(before_state.get("attentionScore")),
            3,
        ),
        "toAttentionScore": round(
            _safe_float(after_state.get("attentionScore")),
            3,
        ),
        "attentionScoreDelta": round(
            _safe_float(after_state.get("attentionScore"))
            - _safe_float(before_state.get("attentionScore")),
            3,
        ),
        "fromWorkloadUnits": round(
            _safe_float(before_state.get("workloadUnits")),
            2,
        ),
        "toWorkloadUnits": round(
            _safe_float(after_state.get("workloadUnits")),
            2,
        ),
        "workloadUnitsDelta": round(
            _safe_float(after_state.get("workloadUnits"))
            - _safe_float(before_state.get("workloadUnits")),
            2,
        ),
        "fromCoverageGaps": before_gaps,
        "toCoverageGaps": after_gaps,
        "coverageGapDelta": len(after_gaps) - len(before_gaps),
        "interpretation": (
            "This is deterministic operational-state differencing. "
            "A transition does not prove improvement or deterioration "
            "of physical component condition."
        ),
    }


def compare_fleet_states(
    before_records: list[dict[str, Any]],
    after_records: list[dict[str, Any]],
) -> dict[str, Any]:
    before_map = {
        str(record["vehicleId"]): record
        for record in before_records
        if record.get("vehicleId") is not None
    }
    after_map = {
        str(record["vehicleId"]): record
        for record in after_records
        if record.get("vehicleId") is not None
    }

    vehicle_ids = sorted(set(before_map) | set(after_map))

    changes: list[dict[str, Any]] = []

    for vehicle_id in vehicle_ids:
        before = before_map.get(
            vehicle_id,
            {"vehicleId": vehicle_id},
        )
        after = after_map.get(
            vehicle_id,
            {"vehicleId": vehicle_id},
        )

        changes.append(vehicle_state_change(before, after))

    changed = [row for row in changes if row["changed"]]

    transition_counts = {
        transition: sum(
            1
            for row in changes
            if transition in row["transitions"]
        )
        for transition in FLEET_CHANGE_TRANSITIONS
    }

    before_workload = round(
        sum(
            _safe_float(record.get("workloadUnits"))
            for record in before_records
        ),
        2,
    )
    after_workload = round(
        sum(
            _safe_float(record.get("workloadUnits"))
            for record in after_records
        ),
        2,
    )

    before_attention = round(
        sum(
            _safe_float(record.get("attentionScore"))
            for record in before_records
        ),
        3,
    )
    after_attention = round(
        sum(
            _safe_float(record.get("attentionScore"))
            for record in after_records
        ),
        3,
    )

    before_gaps = sum(
        len(record.get("coverageGaps") or [])
        for record in before_records
    )
    after_gaps = sum(
        len(record.get("coverageGaps") or [])
        for record in after_records
    )

    return {
        "rulesVersion": FLEET_CHANGE_RULES_VERSION,
        "fromVehicleCount": len(before_records),
        "toVehicleCount": len(after_records),
        "vehiclesCompared": len(vehicle_ids),
        "vehiclesChanged": len(changed),
        "vehiclesUnchanged": len(vehicle_ids) - len(changed),
        "transitionCounts": transition_counts,
        "fromWorkloadUnits": before_workload,
        "toWorkloadUnits": after_workload,
        "workloadUnitsDelta": round(
            after_workload - before_workload,
            2,
        ),
        "fromAttentionScoreTotal": before_attention,
        "toAttentionScoreTotal": after_attention,
        "attentionScoreTotalDelta": round(
            after_attention - before_attention,
            3,
        ),
        "fromCoverageGapInstances": before_gaps,
        "toCoverageGapInstances": after_gaps,
        "coverageGapInstanceDelta": after_gaps - before_gaps,
        "vehicleChanges": changes,
        "interpretation": (
            "Fleet State Change compares persisted or selected-run derived "
            "operational state. Changes describe workflow/evidence state, "
            "not physical failure progression, causal effects, component "
            "condition, or validated reliability change."
        ),
    }
