"""Decision Queue & Approval Orchestration rules for FleetMind Phase 8.1.

Queue priority, age buckets, and review targets are deterministic internal
workflow conventions.

They are not:
- physical safety deadlines
- technician-hour estimates
- maintenance duration estimates
- calibrated failure risk
- physical severity
- service-level commitments
- causal evidence
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fleetmind_common.closed_loop_rules import (
    CLOSED_LOOP_PRIORITIES,
    CLOSED_LOOP_STATES,
    PRIORITY_ORDER,
    STATE_CANCELLED,
    STATE_EXECUTED,
    STATE_REJECTED,
    STATE_SUPERSEDED,
)


DECISION_QUEUE_RULES_VERSION = "fm-decision-queue-8.1-v1"


AGE_NEW = "NEW"
AGE_AGING = "AGING"
AGE_OVERDUE = "OVERDUE"
AGE_STALE = "STALE"

DECISION_QUEUE_AGE_BUCKETS = (
    AGE_NEW,
    AGE_AGING,
    AGE_OVERDUE,
    AGE_STALE,
)


# Internal workflow-review targets only.
PRIORITY_REVIEW_TARGET_HOURS = {
    "P0": 4.0,
    "P1": 12.0,
    "P2": 24.0,
    "P3": 72.0,
}


TERMINAL_QUEUE_STATUSES = (
    STATE_EXECUTED,
    STATE_REJECTED,
    STATE_CANCELLED,
    STATE_SUPERSEDED,
)


def _utc(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def queue_age_hours(
    created_at: datetime,
    now: datetime,
) -> float:
    """Return non-negative elapsed workflow age."""

    elapsed = (
        _utc(now)
        - _utc(created_at)
    ).total_seconds() / 3600.0

    return round(
        max(0.0, elapsed),
        3,
    )


def age_bucket(
    age_hours: float,
) -> str:
    age = max(
        0.0,
        float(age_hours),
    )

    if age < 4.0:
        return AGE_NEW

    if age < 24.0:
        return AGE_AGING

    if age < 72.0:
        return AGE_OVERDUE

    return AGE_STALE


def review_target_hours(
    priority: str,
) -> float:
    if priority not in CLOSED_LOOP_PRIORITIES:
        raise ValueError(
            "Unsupported decision-queue priority: "
            f"{priority}"
        )

    return float(
        PRIORITY_REVIEW_TARGET_HOURS[
            priority
        ]
    )


def review_target_overdue(
    priority: str,
    age_hours: float,
) -> bool:
    return (
        float(age_hours)
        >= review_target_hours(
            priority
        )
    )


def active_queue_status(
    status: str,
) -> bool:
    if status not in CLOSED_LOOP_STATES:
        raise ValueError(
            "Unsupported closed-loop status: "
            f"{status}"
        )

    return (
        status
        not in TERMINAL_QUEUE_STATUSES
    )


def assignment_allowed(
    status: str,
) -> bool:
    """Assignment is allowed only while the recommendation is active."""

    return active_queue_status(
        status
    )


def decision_queue_record(
    recommendation: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    """Project one persisted recommendation into queue metadata."""

    priority = str(
        recommendation.get(
            "priority"
        )
        or "P3"
    )

    if priority not in CLOSED_LOOP_PRIORITIES:
        raise ValueError(
            "Unsupported decision-queue priority: "
            f"{priority}"
        )

    status = str(
        recommendation.get(
            "status"
        )
        or ""
    )

    if status not in CLOSED_LOOP_STATES:
        raise ValueError(
            "Unsupported closed-loop status: "
            f"{status}"
        )

    created_at = recommendation.get(
        "createdAt"
    )

    if not isinstance(
        created_at,
        datetime,
    ):
        raise ValueError(
            "createdAt must be a datetime"
        )

    hours = queue_age_hours(
        created_at,
        now,
    )

    assigned_to = recommendation.get(
        "assignedTo"
    )

    return {
        "id": recommendation.get("id"),
        "runId": recommendation.get(
            "runId"
        ),
        "experimentId": (
            recommendation.get(
                "experimentId"
            )
        ),
        "vehicleId": recommendation.get(
            "vehicleId"
        ),
        "caseId": recommendation.get(
            "caseId"
        ),
        "recommendationType": (
            recommendation.get(
                "recommendationType"
            )
        ),
        "priority": priority,
        "priorityRank": (
            PRIORITY_ORDER[
                priority
            ]
        ),
        "status": status,
        "active": active_queue_status(
            status
        ),
        "approvalRequired": bool(
            recommendation.get(
                "approvalRequired",
                True,
            )
        ),
        "assignedTo": assigned_to,
        "assignedAt": (
            recommendation.get(
                "assignedAt"
            )
        ),
        "unassigned": not bool(
            assigned_to
        ),
        "ageHours": hours,
        "ageBucket": age_bucket(
            hours
        ),
        "reviewTargetHours": (
            review_target_hours(
                priority
            )
        ),
        "reviewTargetOverdue": (
            review_target_overdue(
                priority,
                hours,
            )
        ),
        "createdAt": created_at,
        "updatedAt": recommendation.get(
            "updatedAt"
        ),
    }


def decision_queue_rows(
    recommendations: list[
        dict[str, Any]
    ],
    *,
    now: datetime,
    include_terminal: bool = False,
) -> list[dict[str, Any]]:
    """Build deterministic operational queue ordering."""

    rows = [
        decision_queue_record(
            recommendation,
            now=now,
        )
        for recommendation
        in recommendations
    ]

    if not include_terminal:
        rows = [
            row
            for row in rows
            if row["active"]
        ]

    rows.sort(
        key=lambda row: (
            int(
                row["priorityRank"]
            ),
            -int(
                bool(
                    row[
                        "reviewTargetOverdue"
                    ]
                )
            ),
            -int(
                bool(
                    row["unassigned"]
                )
            ),
            -float(
                row["ageHours"]
            ),
            int(
                row.get("id")
                or 0
            ),
        )
    )

    for rank, row in enumerate(
        rows,
        start=1,
    ):
        row["queueRank"] = rank

    return rows


def decision_queue_summary(
    recommendations: list[
        dict[str, Any]
    ],
    *,
    now: datetime,
) -> dict[str, Any]:
    rows = [
        decision_queue_record(
            recommendation,
            now=now,
        )
        for recommendation
        in recommendations
    ]

    active = [
        row
        for row in rows
        if row["active"]
    ]

    return {
        "rulesVersion": (
            DECISION_QUEUE_RULES_VERSION
        ),
        "totalRecommendations": len(
            rows
        ),
        "activeRecommendations": len(
            active
        ),
        "terminalRecommendations": (
            len(rows)
            - len(active)
        ),
        "unassignedActive": sum(
            1
            for row in active
            if row["unassigned"]
        ),
        "overdueActive": sum(
            1
            for row in active
            if row[
                "reviewTargetOverdue"
            ]
        ),
        "byPriority": [
            {
                "priority": priority,
                "active": sum(
                    1
                    for row in active
                    if row["priority"]
                    == priority
                ),
            }
            for priority
            in CLOSED_LOOP_PRIORITIES
        ],
        "byStatus": [
            {
                "status": status,
                "count": sum(
                    1
                    for row in rows
                    if row["status"]
                    == status
                ),
            }
            for status
            in CLOSED_LOOP_STATES
        ],
        "byAgeBucket": [
            {
                "ageBucket": bucket,
                "active": sum(
                    1
                    for row in active
                    if row["ageBucket"]
                    == bucket
                ),
            }
            for bucket
            in DECISION_QUEUE_AGE_BUCKETS
        ],
        "interpretation": {
            "workflowQueueOnly": True,
            "ageIsPhysicalCondition": False,
            "priorityIsPhysicalRisk": False,
            "reviewTargetIsSafetyDeadline": False,
            "reviewTargetIsContractualSla": False,
            "technicianHours": False,
            "physicalMaintenanceDuration": False,
            "causalAttribution": False,
        },
    }
