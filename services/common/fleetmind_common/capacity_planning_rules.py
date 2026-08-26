from __future__ import annotations

from collections import defaultdict
from typing import Any


CAPACITY_PLANNING_RULES_VERSION = "fm-capacity-planning-7.4-v1"

STRATEGY_ATTENTION_FIRST = "ATTENTION_FIRST"
STRATEGY_URGENT_FIRST = "URGENT_FIRST"
STRATEGY_COVERAGE_GAP_FIRST = "COVERAGE_GAP_FIRST"
STRATEGY_WORKLOAD_EFFICIENCY = "WORKLOAD_EFFICIENCY"
STRATEGY_BALANCED = "BALANCED"

CAPACITY_PLANNING_STRATEGIES = (
    STRATEGY_ATTENTION_FIRST,
    STRATEGY_URGENT_FIRST,
    STRATEGY_COVERAGE_GAP_FIRST,
    STRATEGY_WORKLOAD_EFFICIENCY,
    STRATEGY_BALANCED,
)

TIER_RANK = {
    "URGENT_REVIEW": 4,
    "PLAN_SERVICE": 3,
    "MONITOR": 2,
    "ROUTINE_REVIEW": 1,
    None: 0,
}

DECISION_STATE_RANK = {
    "WORKFLOW_ACTIVE": 4,
    "PLAN": 3,
    "INVESTIGATE": 2,
    "OBSERVE": 1,
    "NOMINAL": 0,
}


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _workload(record: dict[str, Any]) -> float:
    return max(0.0, _safe_float(record.get("workloadUnits")))


def _attention(record: dict[str, Any]) -> float:
    return max(0.0, _safe_float(record.get("attentionScore")))


def _gap_count(record: dict[str, Any]) -> int:
    return len(record.get("coverageGaps") or [])


def _tier_rank(record: dict[str, Any]) -> int:
    return TIER_RANK.get(record.get("maintenanceTier"), 0)


def _decision_rank(record: dict[str, Any]) -> int:
    return DECISION_STATE_RANK.get(
        record.get("decisionState"),
        0,
    )


def _efficiency(record: dict[str, Any]) -> float:
    workload = _workload(record)

    if workload <= 0.0:
        return 0.0

    return round(
        (
            _attention(record)
            + (_gap_count(record) * 8.0)
            + (_tier_rank(record) * 5.0)
        )
        / workload,
        6,
    )


def _strategy_key(
    record: dict[str, Any],
    strategy: str,
) -> tuple:
    vehicle_id = str(record.get("vehicleId") or "")

    if strategy == STRATEGY_ATTENTION_FIRST:
        return (
            -_attention(record),
            -_tier_rank(record),
            -_gap_count(record),
            _workload(record),
            vehicle_id,
        )

    if strategy == STRATEGY_URGENT_FIRST:
        return (
            -_tier_rank(record),
            -_attention(record),
            -_gap_count(record),
            _workload(record),
            vehicle_id,
        )

    if strategy == STRATEGY_COVERAGE_GAP_FIRST:
        return (
            -_gap_count(record),
            -_attention(record),
            -_tier_rank(record),
            _workload(record),
            vehicle_id,
        )

    if strategy == STRATEGY_WORKLOAD_EFFICIENCY:
        return (
            -_efficiency(record),
            -_attention(record),
            _workload(record),
            vehicle_id,
        )

    if strategy == STRATEGY_BALANCED:
        return (
            -_decision_rank(record),
            -_tier_rank(record),
            -_gap_count(record),
            -_attention(record),
            _workload(record),
            vehicle_id,
        )

    raise ValueError(
        f"Unsupported capacity planning strategy: {strategy}"
    )


def eligible_capacity_records(
    records: list[dict[str, Any]],
    *,
    allowed_maintenance_tiers: list[str] | None = None,
    allowed_decision_states: list[str] | None = None,
) -> list[dict[str, Any]]:
    tiers = (
        set(allowed_maintenance_tiers)
        if allowed_maintenance_tiers
        else None
    )
    states = (
        set(allowed_decision_states)
        if allowed_decision_states
        else None
    )

    eligible: list[dict[str, Any]] = []

    for record in records:
        if _workload(record) <= 0.0:
            continue

        if (
            tiers is not None
            and record.get("maintenanceTier") not in tiers
        ):
            continue

        if (
            states is not None
            and record.get("decisionState") not in states
        ):
            continue

        eligible.append(record)

    return eligible


def _rollup(
    records: list[dict[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "vehicles": 0,
            "workloadUnits": 0.0,
            "coverageGapInstances": 0,
        }
    )

    for record in records:
        raw = record.get(field)
        value = "NONE" if raw is None else str(raw)

        grouped[value]["vehicles"] += 1
        grouped[value]["workloadUnits"] += _workload(record)
        grouped[value]["coverageGapInstances"] += _gap_count(record)

    return [
        {
            field: value,
            "vehicles": values["vehicles"],
            "workloadUnits": round(
                values["workloadUnits"],
                2,
            ),
            "coverageGapInstances": (
                values["coverageGapInstances"]
            ),
        }
        for value, values in sorted(grouped.items())
    ]


def simulate_capacity_plan(
    records: list[dict[str, Any]],
    *,
    capacity_units: float,
    strategy: str,
    max_vehicles: int | None = None,
    allowed_maintenance_tiers: list[str] | None = None,
    allowed_decision_states: list[str] | None = None,
) -> dict[str, Any]:
    """
    Allocate synthetic workflow-capacity units to whole vehicle records.

    A vehicle is selected only when all of its synthetic workload units fit
    within remaining capacity. No partial vehicle allocation is performed.

    This is not technician scheduling, technician hours, physical maintenance
    effort, failure-risk reduction, RUL, causal maintenance effect, or an
    automatic workflow execution.
    """
    if strategy not in CAPACITY_PLANNING_STRATEGIES:
        raise ValueError(
            f"Unsupported capacity planning strategy: {strategy}"
        )

    if capacity_units < 0.0:
        raise ValueError("capacity_units must be non-negative")

    if max_vehicles is not None and max_vehicles < 1:
        raise ValueError("max_vehicles must be at least 1")

    eligible = eligible_capacity_records(
        records,
        allowed_maintenance_tiers=allowed_maintenance_tiers,
        allowed_decision_states=allowed_decision_states,
    )

    ordered = sorted(
        eligible,
        key=lambda record: _strategy_key(
            record,
            strategy,
        ),
    )

    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    remaining = round(float(capacity_units), 6)

    for record in ordered:
        if (
            max_vehicles is not None
            and len(selected) >= max_vehicles
        ):
            deferred.append(record)
            continue

        required = _workload(record)

        if required <= remaining + 1e-9:
            selected.append(record)
            remaining = round(
                max(0.0, remaining - required),
                6,
            )
        else:
            deferred.append(record)

    total_workload = round(
        sum(_workload(record) for record in records),
        2,
    )
    eligible_workload = round(
        sum(_workload(record) for record in eligible),
        2,
    )
    selected_workload = round(
        sum(_workload(record) for record in selected),
        2,
    )
    deferred_workload = round(
        sum(_workload(record) for record in deferred),
        2,
    )

    total_gap_instances = sum(
        _gap_count(record)
        for record in records
    )
    selected_gap_instances = sum(
        _gap_count(record)
        for record in selected
    )

    utilization = (
        round(
            (selected_workload / capacity_units) * 100.0,
            3,
        )
        if capacity_units > 0.0
        else 0.0
    )

    selected_rows = [
        {
            "rank": index,
            "vehicleId": record.get("vehicleId"),
            "decisionState": record.get("decisionState"),
            "maintenanceTier": record.get("maintenanceTier"),
            "hypothesisClass": record.get("topClass"),
            "attentionScore": round(
                _attention(record),
                3,
            ),
            "workloadUnits": round(
                _workload(record),
                2,
            ),
            "coverageGapCount": _gap_count(record),
            "coverageGaps": list(
                record.get("coverageGaps") or []
            ),
            "strategyEfficiency": _efficiency(record),
        }
        for index, record in enumerate(
            selected,
            start=1,
        )
    ]

    return {
        "rulesVersion": CAPACITY_PLANNING_RULES_VERSION,
        "strategy": strategy,
        "requestedCapacityUnits": round(
            float(capacity_units),
            2,
        ),
        "allocatedCapacityUnits": selected_workload,
        "unusedCapacityUnits": round(
            max(0.0, float(capacity_units) - selected_workload),
            2,
        ),
        "capacityUtilizationPct": utilization,
        "fleetVehicles": len(records),
        "eligibleVehicles": len(eligible),
        "selectedVehicles": len(selected),
        "deferredVehicles": len(deferred),
        "ineligibleVehicles": len(records) - len(eligible),
        "fleetWorkloadUnits": total_workload,
        "eligibleWorkloadUnits": eligible_workload,
        "selectedWorkloadUnits": selected_workload,
        "deferredWorkloadUnits": deferred_workload,
        "fleetCoverageGapInstances": total_gap_instances,
        "simulatedAddressedCoverageGapInstances": (
            selected_gap_instances
        ),
        "simulatedRemainingCoverageGapInstances": (
            total_gap_instances - selected_gap_instances
        ),
        "selection": selected_rows,
        "selectedByMaintenanceTier": _rollup(
            selected,
            "maintenanceTier",
        ),
        "selectedByDecisionState": _rollup(
            selected,
            "decisionState",
        ),
        "selectedByHypothesisClass": _rollup(
            selected,
            "topClass",
        ),
        "constraints": {
            "maxVehicles": max_vehicles,
            "allowedMaintenanceTiers": (
                list(allowed_maintenance_tiers)
                if allowed_maintenance_tiers
                else []
            ),
            "allowedDecisionStates": (
                list(allowed_decision_states)
                if allowed_decision_states
                else []
            ),
        },
        "interpretation": (
            "This simulation allocates synthetic workflow prioritization units "
            "to selected vehicle records. Units are not technician hours or "
            "physical service duration. Simulated addressed gaps assume the "
            "selected workflow capacity is applied; they are not evidence that "
            "a gap or physical condition was actually resolved."
        ),
    }
