"""Fleet Command Center rules for FleetMind Phase 7.7.

This module composes selected-run operational state into deterministic command
queues. Queue placement and ordering describe workflow priority only.

They are not:
- calibrated physical failure risk
- safety probability
- physical component condition
- physical RUL
- causal attribution
- technician-hour estimates
"""

from __future__ import annotations

from typing import Any


FLEET_COMMAND_RULES_VERSION = "fm-fleet-command-7.7-v1"

QUEUE_HIGHEST_ATTENTION = "HIGHEST_ATTENTION"
QUEUE_URGENT_REVIEW = "URGENT_REVIEW"
QUEUE_PLAN_SERVICE = "PLAN_SERVICE"
QUEUE_COVERAGE_GAPS = "COVERAGE_GAPS"
QUEUE_PENDING_APPROVAL = "PENDING_APPROVAL"
QUEUE_UNASSIGNED_CASES = "UNASSIGNED_CASES"
QUEUE_TRAJECTORY_INELIGIBLE = "TRAJECTORY_INELIGIBLE"

FLEET_COMMAND_QUEUES = (
    QUEUE_HIGHEST_ATTENTION,
    QUEUE_URGENT_REVIEW,
    QUEUE_PLAN_SERVICE,
    QUEUE_COVERAGE_GAPS,
    QUEUE_PENDING_APPROVAL,
    QUEUE_UNASSIGNED_CASES,
    QUEUE_TRAJECTORY_INELIGIBLE,
)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def queue_match(
    record: dict[str, Any],
    queue: str,
) -> bool:
    """Return whether a fleet record belongs in an operational command queue."""

    if queue not in FLEET_COMMAND_QUEUES:
        raise ValueError(
            f"Unsupported Fleet Command queue: {queue}"
        )

    if queue == QUEUE_HIGHEST_ATTENTION:
        return (
            str(
                record.get("decisionState")
                or "NOMINAL"
            )
            != "NOMINAL"
        )

    if queue == QUEUE_URGENT_REVIEW:
        return (
            record.get("maintenanceTier")
            == "URGENT_REVIEW"
        )

    if queue == QUEUE_PLAN_SERVICE:
        return (
            record.get("maintenanceTier")
            == "PLAN_SERVICE"
        )

    if queue == QUEUE_COVERAGE_GAPS:
        return bool(
            record.get("coverageGaps")
        )

    if queue == QUEUE_PENDING_APPROVAL:
        statuses = set(
            record.get("automationStatuses")
            or []
        )

        return (
            "PENDING_APPROVAL" in statuses
            or record.get("automationStatus")
            == "PENDING_APPROVAL"
        )

    if queue == QUEUE_UNASSIGNED_CASES:
        return (
            record.get("caseId") is not None
            and not record.get("assignedTo")
        )

    if queue == QUEUE_TRAJECTORY_INELIGIBLE:
        return (
            record.get("trajectoryEligible")
            is False
        )

    return False


def command_queue_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Project a selected-run fleet record into command-center queue metadata."""

    queues = [
        queue
        for queue in FLEET_COMMAND_QUEUES
        if queue_match(record, queue)
    ]

    return {
        "vehicleId": record.get("vehicleId"),
        "topClass": record.get("topClass"),
        "topConfidence": round(
            _number(
                record.get("topConfidence")
            ),
            6,
        ),
        "decisionState": record.get(
            "decisionState"
        ),
        "attentionScore": round(
            _number(
                record.get("attentionScore")
            ),
            3,
        ),
        "workloadUnits": round(
            _number(
                record.get("workloadUnits")
            ),
            2,
        ),
        "maintenanceTier": record.get(
            "maintenanceTier"
        ),
        "reviewPriority": record.get(
            "reviewPriority"
        ),
        "caseId": record.get("caseId"),
        "assignedTo": record.get(
            "assignedTo"
        ),
        "trajectoryEligible": record.get(
            "trajectoryEligible"
        ),
        "coverageGaps": list(
            record.get("coverageGaps")
            or []
        ),
        "automationStatus": record.get(
            "automationStatus"
        ),
        "queues": queues,
    }


def command_queue_rows(
    records: list[dict[str, Any]],
    queue: str,
) -> list[dict[str, Any]]:
    """Return stable deterministic ordering for one operational queue."""

    if queue not in FLEET_COMMAND_QUEUES:
        raise ValueError(
            f"Unsupported Fleet Command queue: {queue}"
        )

    rows = [
        command_queue_record(record)
        for record in records
        if queue_match(record, queue)
    ]

    rows.sort(
        key=lambda row: (
            -_number(
                row.get("attentionScore")
            ),
            -_number(
                row.get("workloadUnits")
            ),
            -_number(
                row.get("topConfidence")
            ),
            str(
                row.get("vehicleId")
                or ""
            ),
        )
    )

    for rank, row in enumerate(
        rows,
        start=1,
    ):
        row["queue"] = queue
        row["queueRank"] = rank

    return rows


def queue_counts(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return population counts for every supported command queue."""

    return [
        {
            "queue": queue,
            "vehicles": sum(
                1
                for record in records
                if queue_match(
                    record,
                    queue,
                )
            ),
        }
        for queue in FLEET_COMMAND_QUEUES
    ]


def command_center_summary(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a fleet command summary from selected-run operational records."""

    decision_states = sorted(
        {
            str(
                record.get(
                    "decisionState"
                )
                or "UNKNOWN"
            )
            for record in records
        }
    )

    state_counts = [
        {
            "state": state,
            "vehicles": sum(
                1
                for record in records
                if str(
                    record.get(
                        "decisionState"
                    )
                    or "UNKNOWN"
                )
                == state
            ),
        }
        for state in decision_states
    ]

    coverage_gap_instances = sum(
        len(
            record.get("coverageGaps")
            or []
        )
        for record in records
    )

    attention_records = [
        record
        for record in records
        if str(
            record.get(
                "decisionState"
            )
            or "NOMINAL"
        )
        != "NOMINAL"
    ]

    return {
        "rulesVersion": (
            FLEET_COMMAND_RULES_VERSION
        ),
        "totalVehicles": len(records),
        "nonHealthyHypotheses": sum(
            1
            for record in records
            if str(
                record.get("topClass")
                or "healthy"
            )
            != "healthy"
        ),
        "vehiclesWithCases": sum(
            1
            for record in records
            if record.get("caseId")
            is not None
        ),
        "attentionRequired": len(
            attention_records
        ),
        "vehiclesWithCoverageGaps": sum(
            1
            for record in records
            if record.get("coverageGaps")
        ),
        "coverageGapInstances": (
            coverage_gap_instances
        ),
        "totalWorkloadUnits": round(
            sum(
                _number(
                    record.get(
                        "workloadUnits"
                    )
                )
                for record in records
            ),
            2,
        ),
        "meanAttentionScore": round(
            (
                sum(
                    _number(
                        record.get(
                            "attentionScore"
                        )
                    )
                    for record
                    in attention_records
                )
                / len(
                    attention_records
                )
            )
            if attention_records
            else 0.0,
            3,
        ),
        "byDecisionState": state_counts,
        "queues": queue_counts(records),
        "interpretation": {
            "operationalCommandLayerOnly": True,
            "queuePriorityIsPhysicalRisk": False,
            "physicalFailureProbability": False,
            "physicalConditionProof": False,
            "physicalRul": False,
            "causalAttribution": False,
            "technicianHours": False,
        },
    }


def command_vehicle_rows(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the full command population in deterministic priority order."""

    rows = [
        command_queue_record(record)
        for record in records
    ]

    rows.sort(
        key=lambda row: (
            -_number(
                row.get("attentionScore")
            ),
            -_number(
                row.get("workloadUnits")
            ),
            -_number(
                row.get("topConfidence")
            ),
            str(
                row.get("vehicleId")
                or ""
            ),
        )
    )

    return rows
