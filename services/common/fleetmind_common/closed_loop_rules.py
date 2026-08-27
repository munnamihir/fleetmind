"""Closed-loop operational recommendation rules for FleetMind Phase 8.0.

FleetMind recommendations are human-controlled workflow metadata.

A recommendation is not:
- a physical maintenance command
- an actuator command
- proof that a component failed
- proof that a repair occurred
- a calibrated safety decision
- autonomous vehicle control

The lifecycle deliberately separates:
evaluation -> acknowledgement -> approval -> execution readiness -> execution.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


CLOSED_LOOP_RULES_VERSION = "fm-closed-loop-operations-8.0-v1"


# ---------------------------------------------------------------------------
# Recommendation types
# ---------------------------------------------------------------------------

RECOMMENDATION_REVIEW_CASE = "REVIEW_CASE"
RECOMMENDATION_ASSIGN_CASE = "ASSIGN_CASE"
RECOMMENDATION_CREATE_REVIEW_PLAN = "CREATE_REVIEW_PLAN"
RECOMMENDATION_ADD_WATCHLIST = "ADD_WATCHLIST"
RECOMMENDATION_REVIEW_AUTOMATION_ACTION = "REVIEW_AUTOMATION_ACTION"

CLOSED_LOOP_RECOMMENDATION_TYPES = (
    RECOMMENDATION_REVIEW_CASE,
    RECOMMENDATION_ASSIGN_CASE,
    RECOMMENDATION_CREATE_REVIEW_PLAN,
    RECOMMENDATION_ADD_WATCHLIST,
    RECOMMENDATION_REVIEW_AUTOMATION_ACTION,
)


# ---------------------------------------------------------------------------
# Lifecycle states
# ---------------------------------------------------------------------------

STATE_PROPOSED = "PROPOSED"
STATE_ACKNOWLEDGED = "ACKNOWLEDGED"
STATE_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
STATE_APPROVED = "APPROVED"
STATE_EXECUTION_READY = "EXECUTION_READY"
STATE_EXECUTED = "EXECUTED"

STATE_REJECTED = "REJECTED"
STATE_CANCELLED = "CANCELLED"
STATE_SUPERSEDED = "SUPERSEDED"

CLOSED_LOOP_STATES = (
    STATE_PROPOSED,
    STATE_ACKNOWLEDGED,
    STATE_APPROVAL_REQUIRED,
    STATE_APPROVED,
    STATE_EXECUTION_READY,
    STATE_EXECUTED,
    STATE_REJECTED,
    STATE_CANCELLED,
    STATE_SUPERSEDED,
)

TERMINAL_STATES = (
    STATE_EXECUTED,
    STATE_REJECTED,
    STATE_CANCELLED,
    STATE_SUPERSEDED,
)


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS = {
    STATE_PROPOSED: (
        STATE_ACKNOWLEDGED,
        STATE_REJECTED,
        STATE_CANCELLED,
        STATE_SUPERSEDED,
    ),
    STATE_ACKNOWLEDGED: (
        STATE_APPROVAL_REQUIRED,
        STATE_REJECTED,
        STATE_CANCELLED,
        STATE_SUPERSEDED,
    ),
    STATE_APPROVAL_REQUIRED: (
        STATE_APPROVED,
        STATE_REJECTED,
        STATE_CANCELLED,
        STATE_SUPERSEDED,
    ),
    STATE_APPROVED: (
        STATE_EXECUTION_READY,
        STATE_CANCELLED,
        STATE_SUPERSEDED,
    ),
    STATE_EXECUTION_READY: (
        STATE_EXECUTED,
        STATE_CANCELLED,
        STATE_SUPERSEDED,
    ),
    STATE_EXECUTED: (),
    STATE_REJECTED: (),
    STATE_CANCELLED: (),
    STATE_SUPERSEDED: (),
}


# ---------------------------------------------------------------------------
# Recommendation priorities
# ---------------------------------------------------------------------------

PRIORITY_P0 = "P0"
PRIORITY_P1 = "P1"
PRIORITY_P2 = "P2"
PRIORITY_P3 = "P3"

CLOSED_LOOP_PRIORITIES = (
    PRIORITY_P0,
    PRIORITY_P1,
    PRIORITY_P2,
    PRIORITY_P3,
)

PRIORITY_ORDER = {
    PRIORITY_P0: 0,
    PRIORITY_P1: 1,
    PRIORITY_P2: 2,
    PRIORITY_P3: 3,
}


def validate_recommendation_type(
    recommendation_type: str,
) -> None:
    if (
        recommendation_type
        not in CLOSED_LOOP_RECOMMENDATION_TYPES
    ):
        raise ValueError(
            "Unsupported closed-loop recommendation type: "
            f"{recommendation_type}"
        )


def validate_state(state: str) -> None:
    if state not in CLOSED_LOOP_STATES:
        raise ValueError(
            f"Unsupported closed-loop state: {state}"
        )


def validate_priority(priority: str) -> None:
    if priority not in CLOSED_LOOP_PRIORITIES:
        raise ValueError(
            f"Unsupported closed-loop priority: {priority}"
        )


def allowed_next_states(
    state: str,
) -> tuple[str, ...]:
    validate_state(state)

    return tuple(
        ALLOWED_TRANSITIONS[state]
    )


def can_transition(
    from_state: str,
    to_state: str,
) -> bool:
    validate_state(from_state)
    validate_state(to_state)

    return (
        to_state
        in ALLOWED_TRANSITIONS[from_state]
    )


def require_transition(
    from_state: str,
    to_state: str,
) -> None:
    """Raise when a lifecycle state jump violates the human-control gate."""

    if not can_transition(
        from_state,
        to_state,
    ):
        raise ValueError(
            "Invalid closed-loop transition: "
            f"{from_state} -> {to_state}"
        )


def is_terminal_state(
    state: str,
) -> bool:
    validate_state(state)

    return state in TERMINAL_STATES


def approval_required_before_execution() -> bool:
    """Explicit contract consumed by API/UI tests."""

    return True


def recommendation_key(
    *,
    run_id: int,
    experiment_id: str,
    vehicle_id: str,
    recommendation_type: str,
    case_id: int | None = None,
    source_key: str | None = None,
) -> str:
    """Create deterministic materialization identity.

    Re-evaluating the same selected-run recommendation target should produce
    the same key so persistence can remain idempotent.
    """

    validate_recommendation_type(
        recommendation_type
    )

    payload = {
        "runId": int(run_id),
        "experimentId": str(
            experiment_id
        ),
        "vehicleId": str(vehicle_id),
        "recommendationType": (
            recommendation_type
        ),
        "caseId": case_id,
        "sourceKey": (
            str(source_key)
            if source_key is not None
            else None
        ),
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def recommendation_priority(
    record: dict[str, Any],
    recommendation_type: str,
) -> str:
    """Derive deterministic operational urgency.

    P0/P1/P2/P3 are workflow urgency labels only. They do not encode physical
    danger, safety probability, failure probability, or severity of damage.
    """

    validate_recommendation_type(
        recommendation_type
    )

    review_priority = record.get(
        "reviewPriority"
    )
    maintenance_tier = record.get(
        "maintenanceTier"
    )
    episode_state = record.get(
        "episodeState"
    )
    attention_score = float(
        record.get("attentionScore")
        or 0.0
    )

    if (
        review_priority == "HIGH"
        and maintenance_tier
        == "URGENT_REVIEW"
    ):
        return PRIORITY_P0

    if (
        maintenance_tier
        in (
            "URGENT_REVIEW",
            "PLAN_SERVICE",
        )
        or episode_state
        == "DESTABILIZED"
        or attention_score >= 75.0
    ):
        return PRIORITY_P1

    if (
        review_priority
        in ("HIGH", "MEDIUM")
        or attention_score >= 40.0
    ):
        return PRIORITY_P2

    return PRIORITY_P3


def recommendation_candidates(
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    """Derive deterministic human-review recommendations from one vehicle.

    This function creates recommendation candidates only. It performs no
    writes, approvals, executions, maintenance actions, or physical commands.
    """

    vehicle_id = str(
        record.get("vehicleId")
        or ""
    )

    if not vehicle_id:
        raise ValueError(
            "vehicleId is required"
        )

    case_id = record.get("caseId")
    gaps = set(
        record.get("coverageGaps")
        or []
    )
    automation_statuses = set(
        record.get("automationStatuses")
        or []
    )

    candidates: list[
        dict[str, Any]
    ] = []

    def add(
        recommendation_type: str,
        reason: str,
        *,
        source_key: str,
        target_case_id: int | None = None,
    ) -> None:
        candidates.append(
            {
                "vehicleId": vehicle_id,
                "caseId": target_case_id,
                "recommendationType": (
                    recommendation_type
                ),
                "priority": (
                    recommendation_priority(
                        record,
                        recommendation_type,
                    )
                ),
                "reason": reason,
                "sourceKey": source_key,
                "initialState": (
                    STATE_PROPOSED
                ),
                "approvalRequired": True,
                "automaticExecution": False,
                "physicalAction": False,
            }
        )

    # Existing case requiring deliberate operator review.
    if (
        case_id is not None
        and (
            record.get(
                "reviewPriority"
            )
            == "HIGH"
            or record.get(
                "decisionState"
            )
            in (
                "INVESTIGATE",
                "PLAN",
                "WORKFLOW_ACTIVE",
            )
        )
    ):
        add(
            RECOMMENDATION_REVIEW_CASE,
            (
                "Existing diagnostic case "
                "requires operator review."
            ),
            source_key=(
                f"case:{case_id}:review"
            ),
            target_case_id=int(
                case_id
            ),
        )

    if (
        case_id is not None
        and not record.get(
            "assignedTo"
        )
    ):
        add(
            RECOMMENDATION_ASSIGN_CASE,
            (
                "Diagnostic case is "
                "currently unassigned."
            ),
            source_key=(
                f"case:{case_id}:assignment"
            ),
            target_case_id=int(
                case_id
            ),
        )

    if (
        case_id is not None
        and (
            "PRIORITY_CASE_WITHOUT_PLAN"
            in gaps
        )
    ):
        add(
            RECOMMENDATION_CREATE_REVIEW_PLAN,
            (
                "Priority diagnostic case "
                "has no maintenance review plan."
            ),
            source_key=(
                f"case:{case_id}:review-plan"
            ),
            target_case_id=int(
                case_id
            ),
        )

    if (
        case_id is not None
        and (
            "DESTABILIZED_NOT_WATCHLISTED"
            in gaps
        )
    ):
        add(
            RECOMMENDATION_ADD_WATCHLIST,
            (
                "Destabilized diagnostic case "
                "is not currently watchlisted."
            ),
            source_key=(
                f"case:{case_id}:watchlist"
            ),
            target_case_id=int(
                case_id
            ),
        )

    if (
        "PENDING_APPROVAL"
        in automation_statuses
        or record.get(
            "automationStatus"
        )
        == "PENDING_APPROVAL"
        or (
            "PENDING_AUTOMATION_APPROVAL"
            in gaps
        )
    ):
        add(
            (
                RECOMMENDATION_REVIEW_AUTOMATION_ACTION
            ),
            (
                "Automation workflow action "
                "is pending explicit human approval."
            ),
            source_key=(
                "automation:"
                f"{vehicle_id}:pending-approval"
            ),
            target_case_id=(
                int(case_id)
                if case_id
                is not None
                else None
            ),
        )

    candidates.sort(
        key=lambda row: (
            PRIORITY_ORDER[
                row["priority"]
            ],
            row[
                "recommendationType"
            ],
            row[
                "sourceKey"
            ],
        )
    )

    return candidates


def summarize_recommendation_candidates(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize no-write recommendation evaluation."""

    candidates = [
        candidate
        for record in records
        for candidate
        in recommendation_candidates(
            record
        )
    ]

    return {
        "rulesVersion": (
            CLOSED_LOOP_RULES_VERSION
        ),
        "evaluatedVehicles": len(
            records
        ),
        "candidateCount": len(
            candidates
        ),
        "byType": [
            {
                "recommendationType": (
                    recommendation_type
                ),
                "count": sum(
                    1
                    for candidate
                    in candidates
                    if candidate[
                        "recommendationType"
                    ]
                    == recommendation_type
                ),
            }
            for recommendation_type
            in CLOSED_LOOP_RECOMMENDATION_TYPES
        ],
        "byPriority": [
            {
                "priority": priority,
                "count": sum(
                    1
                    for candidate
                    in candidates
                    if candidate[
                        "priority"
                    ]
                    == priority
                ),
            }
            for priority
            in CLOSED_LOOP_PRIORITIES
        ],
        "interpretation": {
            "recommendationsOnly": True,
            "evaluationWrites": False,
            "automaticApproval": False,
            "automaticExecution": False,
            "physicalAction": False,
            "physicalFailureTruth": False,
            "physicalSafetyDecision": False,
            "causalAttribution": False,
        },
    }
