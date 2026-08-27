from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleetmind_common.db import SessionLocal
from fleetmind_common.diagnostic_event_rules import (
    DIAGNOSTIC_EVENT_TYPES,
)
from fleetmind_common.diagnostic_automation_rules import (
    AUTOMATION_ACTION_ENSURE_REVIEW_PLAN,
    AUTOMATION_ACTION_ENSURE_WATCHLIST,
    AUTOMATION_ACTION_STATUSES,
    AUTOMATION_ACTIVITY_ACTION_APPROVED,
    AUTOMATION_ACTIVITY_ACTION_CREATED,
    AUTOMATION_ACTIVITY_ACTION_EXECUTED,
    AUTOMATION_ACTIVITY_ACTION_REJECTED,
    AUTOMATION_ACTIVITY_POLICY_CREATED,
    AUTOMATION_ACTIVITY_POLICY_DISABLED,
    AUTOMATION_ACTIVITY_POLICY_ENABLED,
    AUTOMATION_RULES_VERSION,
    AUTOMATION_STATUS_APPROVED,
    AUTOMATION_STATUS_EXECUTED,
    AUTOMATION_STATUS_PENDING_APPROVAL,
    AUTOMATION_STATUS_REJECTED,
    DEFAULT_AUTOMATION_POLICIES,
    policy_match_reason,
    policy_matches,
)
from fleetmind_common.diagnostic_prognostic_rules import (
    FIT_WINDOW_POINTS,
    MAINTENANCE_ACTIVITY_CREATED,
    MAINTENANCE_ACTIVITY_NOTE_ADDED,
    MAINTENANCE_ACTIVITY_OWNER_CHANGED,
    MAINTENANCE_ACTIVITY_STATE_CHANGED,
    MAINTENANCE_ACTIVITY_TARGET_CHANGED,
    MAINTENANCE_STATES,
    MIN_TRAJECTORY_POINTS,
    PROGNOSTIC_RULES_VERSION,
    TARGET_HYPOTHESIS_CONFIDENCE,
    backtest_threshold_horizon,
    estimate_threshold_horizon,
    fit_trajectory,
    maintenance_priority,
)
from fleetmind_common.diagnostic_pattern_rules import (
    DEFAULT_CLUSTER_MIN_CASES,
    MAX_CLUSTER_CASE_IDS,
    PATTERN_DIMENSIONS,
    PATTERN_RULES_VERSION,
    similarity_score,
)
from fleetmind_common.diagnostic_case_rules import (
    CASE_ACTIVITY_ASSIGNED,
    CASE_ACTIVITY_NOTE_ADDED,
    CASE_ACTIVITY_PRIORITY_CHANGED,
    CASE_ACTIVITY_STATUS_CHANGED,
    CASE_CLOSED,
    DIAGNOSTIC_CASE_PRIORITIES,
    DIAGNOSTIC_CASE_STATUSES,
)
from fleetmind_common.diagnostic_episode_rules import (
    DIAGNOSTIC_EPISODE_STATES,
)
from fleetmind_common.diagnostic_store import (
    DiagnosticAutomationAction,
    DiagnosticAutomationActivity,
    DiagnosticAutomationPolicy,
    DiagnosticCase,
    DiagnosticCaseActivity,
    DiagnosticInvestigationView,
    DiagnosticMaintenanceActivity,
    DiagnosticMaintenancePlan,
    DiagnosticWatchlistEntry,
    DiagnosticVehicleTwinSnapshot,
    DiagnosticEpisode,
    DiagnosticEvent,
    DiagnosticFleetDecisionSnapshot,
    DiagnosticOperationalRecommendation,
    DiagnosticOperationalRecommendationActivity,
    DiagnosticModelRun,
    DiagnosticPrediction,
    DiagnosticReplayPoint,
)
from fleetmind_common.vehicle_twin_rules import (
    VEHICLE_TWIN_RULES_VERSION,
    canonical_twin_state,
    compare_twin_states,
    current_automation_status,
    layer_presence_payload,
    twin_list_record,
)
from fleetmind_common.fleet_twin_rules import (
    FLEET_TWIN_DIMENSIONS,
    FLEET_TWIN_EXPOSURE_MEASURES,
    FLEET_TWIN_RULES_VERSION,
    cohort_exposure_rows,
    compare_cohort_exposure,
    exposure_measure_rate,
    fleet_cohort_exposure,
    fleet_exposure_summary,
)
from fleetmind_common.fleet_change_rules import (
    FLEET_CHANGE_RULES_VERSION,
    FLEET_CHANGE_TRANSITIONS,
    compare_fleet_states,
)
from fleetmind_common.capacity_planning_rules import (
    CAPACITY_PLANNING_RULES_VERSION,
    CAPACITY_PLANNING_STRATEGIES,
    simulate_capacity_plan,
)
from fleetmind_common.workflow_effectiveness_rules import (
    WORKFLOW_EFFECTIVENESS_RULES_VERSION,
    policy_action_effectiveness_rows,
    summarize_policy_effectiveness,
    summarize_workflow_effectiveness,
)
from fleetmind_common.fleet_decision_rules import (
    COHORT_DIMENSIONS,
    COVERAGE_GAPS,
    DECISION_STATES,
    FLEET_DECISION_RULES_VERSION,
    FLEET_DECISION_SCENARIOS,
    apply_workflow_scenario,
    derive_fleet_decision,
    summarize_fleet_records,
)
from fleetmind_common.fleet_command_rules import (
    FLEET_COMMAND_QUEUES,
    FLEET_COMMAND_RULES_VERSION,
    command_center_summary,
    command_queue_rows,
    command_vehicle_rows,
    queue_match,
)
from fleetmind_common.evidence_explainability_rules import (
    EVIDENCE_EXPLAINABILITY_RULES_VERSION,
    attention_score_decomposition,
    evidence_inventory,
    evidence_lineage,
    summarize_attention_explanations,
)
from fleetmind_common.closed_loop_rules import (
    CLOSED_LOOP_PRIORITIES,
    CLOSED_LOOP_RECOMMENDATION_TYPES,
    CLOSED_LOOP_RULES_VERSION,
    CLOSED_LOOP_STATES,
    STATE_ACKNOWLEDGED,
    STATE_APPROVAL_REQUIRED,
    STATE_APPROVED,
    STATE_CANCELLED,
    STATE_EXECUTED,
    STATE_EXECUTION_READY,
    STATE_PROPOSED,
    STATE_REJECTED,
    STATE_SUPERSEDED,
    allowed_next_states,
    recommendation_candidates,
    recommendation_key,
    require_transition,
    summarize_recommendation_candidates,
)
from fleetmind_common.decision_queue_rules import (
    DECISION_QUEUE_RULES_VERSION,
    assignment_allowed,
    decision_queue_rows,
    decision_queue_summary,
)
from fleetmind_common.models import Telemetry


router = APIRouter(
    prefix="/api/v1/diagnostics",
    tags=["diagnostics"],
)


# Phase 6.7 operational transition heuristics.
# Declared before transition results are observed. These are not calibrated
# failure-risk thresholds and must not be described as failure ground truth.
TRANSITION_RECENT_POINTS = 5
TRANSITION_ESCALATION_PER_1K_MILES = 0.01
TRANSITION_STABLE_FRACTION = 0.80
TRANSITION_VOLATILE_FRACTION = 0.60
TRANSITION_VOLATILE_CLASS_CHANGES = 3


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _json_object(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _active_experiment_id(db: Session) -> str | None:
    return db.execute(
        select(Telemetry.experiment_id)
        .where(Telemetry.experiment_id.is_not(None))
        .order_by(desc(Telemetry.id))
        .limit(1)
    ).scalar_one_or_none()


def _latest_run(
    db: Session,
    *,
    experiment_id: str | None = None,
) -> DiagnosticModelRun | None:
    statement = select(DiagnosticModelRun)

    if experiment_id is not None:
        statement = statement.where(
            DiagnosticModelRun.experiment_id == experiment_id
        )

    return db.execute(
        statement
        .order_by(
            desc(DiagnosticModelRun.created_at),
            desc(DiagnosticModelRun.id),
        )
        .limit(1)
    ).scalar_one_or_none()


def _require_current_run(db: Session) -> tuple[str, DiagnosticModelRun]:
    experiment_id = _active_experiment_id(db)
    if experiment_id is None:
        raise HTTPException(
            status_code=503,
            detail="No active tagged telemetry experiment is available",
        )

    run = _latest_run(db, experiment_id=experiment_id)
    if run is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No diagnostic run has been persisted for the active experiment; "
                "run the diagnostic trainer first"
            ),
        )

    return experiment_id, run


@router.get("/status")
def diagnostics_status(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id = _active_experiment_id(db)

    if experiment_id is None:
        return {
            "status": "waiting_for_experiment",
            "experimentId": None,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }

    run = _latest_run(db, experiment_id=experiment_id)

    if run is None:
        return {
            "status": "waiting_for_diagnostic_trainer",
            "experimentId": experiment_id,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }

    report = _json_object(run.report_json)

    return {
        "status": run.status,
        "runId": run.id,
        "experimentId": run.experiment_id,
        "lineage": run.lineage,
        "champion": run.champion,
        "featureCount": run.feature_count,
        "featureSchemaSha256": run.feature_schema_sha256,
        "developmentStatus": run.development_status,
        "benchmarkStatus": run.benchmark_status,
        "snapshotStatus": run.snapshot_status,
        "developmentReadiness": report.get("developmentReadiness"),
        "benchmarkQualification": report.get("benchmarkQualification"),
        "benchmarkSnapshot": report.get("benchmarkSnapshot"),
        "createdAt": run.created_at.isoformat(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/benchmark")
def diagnostics_benchmark(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    report = _json_object(run.report_json)

    benchmark = report.get("benchmark")
    qualification = report.get("benchmarkQualification")
    snapshot = report.get("benchmarkSnapshot")

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "champion": run.champion,
        "qualification": qualification,
        "snapshot": snapshot,
        "benchmark": benchmark,
        "metricsPublishable": (
            isinstance(benchmark, dict)
            and benchmark.get("status") == "qualified"
            and isinstance(benchmark.get("models"), dict)
        ),
    }


@router.get("/vehicles/{vehicle_id}")
def vehicle_diagnostics(
    vehicle_id: str,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)

    prediction = db.execute(
        select(DiagnosticPrediction)
        .where(
            DiagnosticPrediction.run_id == run.id,
            DiagnosticPrediction.vehicle_id == vehicle_id,
        )
        .limit(1)
    ).scalar_one_or_none()

    if prediction is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No diagnostic prediction is available for this vehicle "
                "in the latest active-experiment diagnostic run"
            ),
        )

    latest = db.execute(
        select(Telemetry)
        .where(
            Telemetry.experiment_id == experiment_id,
            Telemetry.vehicle_id == vehicle_id,
        )
        .order_by(desc(Telemetry.id))
        .limit(1)
    ).scalar_one_or_none()

    context = None
    if latest is not None:
        context = {
            "model": latest.model,
            "factory": latest.factory,
            "firmware": latest.firmware,
            "pumpRevision": latest.pump_revision,
            "mileage": round(float(latest.mileage), 1),
        }

    return {
        "vehicleId": vehicle_id,
        "experimentId": experiment_id,
        "runId": run.id,
        "modelLineage": run.lineage,
        "champion": run.champion,
        "generatedAt": prediction.generated_at.isoformat(),
        "anchorTimestamp": prediction.anchor_timestamp.isoformat(),
        "anchorMileage": round(float(prediction.anchor_mileage), 1),
        "topClass": prediction.top_class,
        "topConfidence": round(float(prediction.top_confidence), 6),
        "hypotheses": _json_list(prediction.hypotheses_json),
        "observableEvidence": _json_list(prediction.evidence_json),
        "context": context,
        "interpretationPolicy": (
            "Ranked hypotheses are model outputs from observable telemetry. "
            "They are not direct access to simulator-private failure truth."
        ),
    }


@router.get("/incidents")
def diagnostic_incidents(
    limit: int = Query(default=25, ge=1, le=200),
    min_confidence: float = Query(default=0.50, ge=0.0, le=1.0),
    db: Session = Depends(db_session),
) -> list[dict]:
    experiment_id, run = _require_current_run(db)

    rows = db.execute(
        select(DiagnosticPrediction)
        .where(
            DiagnosticPrediction.run_id == run.id,
            DiagnosticPrediction.top_class != "healthy",
            DiagnosticPrediction.top_confidence >= min_confidence,
        )
        .order_by(
            desc(DiagnosticPrediction.top_confidence),
            desc(DiagnosticPrediction.generated_at),
        )
        .limit(limit)
    ).scalars().all()

    return [
        {
            "vehicleId": row.vehicle_id,
            "experimentId": experiment_id,
            "runId": run.id,
            "topClass": row.top_class,
            "topConfidence": round(float(row.top_confidence), 6),
            "anchorTimestamp": row.anchor_timestamp.isoformat(),
            "anchorMileage": round(float(row.anchor_mileage), 1),
            "hypotheses": _json_list(row.hypotheses_json),
            "observableEvidence": _json_list(row.evidence_json),
        }
        for row in rows
    ]


@router.get("/vehicles/{vehicle_id}/timeline")
def vehicle_diagnostic_timeline(
    vehicle_id: str,
    limit: int = Query(default=64, ge=1, le=256),
    db: Session = Depends(db_session),
) -> dict:
    """Return observable-only replay points from the current diagnostic run."""

    experiment_id, run = _require_current_run(db)
    report = _json_object(run.report_json)
    source = (
        report.get("source")
        if isinstance(report.get("source"), dict)
        else {}
    )
    operational = (
        source.get("operationalScoring")
        if isinstance(source.get("operationalScoring"), dict)
        else {}
    )

    newest_first = db.execute(
        select(DiagnosticReplayPoint)
        .where(
            DiagnosticReplayPoint.run_id == run.id,
            DiagnosticReplayPoint.vehicle_id == vehicle_id,
        )
        .order_by(
            desc(DiagnosticReplayPoint.anchor_timestamp),
            desc(DiagnosticReplayPoint.id),
        )
        .limit(limit)
    ).scalars().all()

    rows = list(reversed(newest_first))

    return {
        "vehicleId": vehicle_id,
        "experimentId": experiment_id,
        "runId": run.id,
        "lineage": run.lineage,
        "champion": run.champion,
        "points": [
            {
                "anchorTimestamp": row.anchor_timestamp.isoformat(),
                "anchorMileage": round(float(row.anchor_mileage), 1),
                "topClass": row.top_class,
                "topConfidence": round(float(row.top_confidence), 6),
                "hypotheses": _json_list(row.hypotheses_json),
                "observableEvidence": _json_list(row.evidence_json),
            }
            for row in rows
        ],
        "historyPolicy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "sameLineageOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
            "rowsPerVehicle": operational.get("historyRowsPerVehicle"),
            "strideSamples": operational.get("replayStrideSamples"),
            "windowSize": operational.get("replayWindowSize"),
        },
        "message": (
            "Replay is derived only from observable telemetry scored by the "
            "current run champion. Hidden simulator failure markers are not "
            "queried or exposed."
            if rows
            else
            "No replay points are persisted for this current run. Run the "
            "Phase 6.6 diagnostic trainer once to populate replay history."
        ),
    }


def _hypothesis_confidence(
    row: DiagnosticReplayPoint,
    target_class: str,
) -> float:
    for hypothesis in _json_list(row.hypotheses_json):
        if (
            isinstance(hypothesis, dict)
            and hypothesis.get("class") == target_class
        ):
            try:
                return float(hypothesis.get("confidence") or 0.0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _transition_record(
    rows: list[DiagnosticReplayPoint],
    *,
    experiment_id: str,
    run_id: int,
    incident_confidence: float,
) -> dict | None:
    if len(rows) < 2:
        return None

    rows = sorted(
        rows,
        key=lambda row: (row.anchor_timestamp, row.id),
    )
    latest = rows[-1]
    first = rows[0]
    recent = rows[-TRANSITION_RECENT_POINTS:]
    latest_class = latest.top_class

    class_changes = sum(
        1
        for previous, current in zip(rows, rows[1:])
        if previous.top_class != current.top_class
    )
    recent_class_changes = sum(
        1
        for previous, current in zip(recent, recent[1:])
        if previous.top_class != current.top_class
    )

    recent_stability = (
        sum(1 for row in recent if row.top_class == latest_class)
        / len(recent)
    )

    start_current_class_confidence = _hypothesis_confidence(
        recent[0],
        latest_class,
    )
    latest_current_class_confidence = _hypothesis_confidence(
        latest,
        latest_class,
    )
    confidence_delta = (
        latest_current_class_confidence
        - start_current_class_confidence
    )

    mileage_delta = max(
        0.0,
        float(latest.anchor_mileage)
        - float(recent[0].anchor_mileage),
    )
    slope_per_1k = (
        confidence_delta / mileage_delta * 1000.0
        if mileage_delta > 0.0
        else 0.0
    )

    newly_emerging = (
        latest_class != "healthy"
        and rows[-2].top_class == "healthy"
        and float(latest.top_confidence) >= incident_confidence
    )

    emergence_points = [
        current
        for previous, current in zip(rows, rows[1:])
        if (
            previous.top_class == "healthy"
            and current.top_class != "healthy"
            and float(current.top_confidence) >= incident_confidence
        )
    ]
    first_emergence = emergence_points[0] if emergence_points else None
    emergence_observed = first_emergence is not None
    escalating = (
        latest_class != "healthy"
        and float(latest.top_confidence) >= incident_confidence
        and slope_per_1k >= TRANSITION_ESCALATION_PER_1K_MILES
    )
    deescalating = (
        latest_class != "healthy"
        and slope_per_1k <= -TRANSITION_ESCALATION_PER_1K_MILES
    )
    volatile = (
        recent_stability < TRANSITION_VOLATILE_FRACTION
        or class_changes >= TRANSITION_VOLATILE_CLASS_CHANGES
    )
    persistent = (
        latest_class != "healthy"
        and float(latest.top_confidence) >= incident_confidence
        and recent_stability >= TRANSITION_STABLE_FRACTION
    )

    if newly_emerging:
        attention_tier = "emerging"
        attention_reason = "healthy → non-healthy at latest anchor"
        sort_rank = 5
    elif escalating:
        attention_tier = "escalating"
        attention_reason = "current-class confidence is rising"
        sort_rank = 4
    elif volatile and latest_class != "healthy":
        attention_tier = "volatile"
        attention_reason = "top hypothesis is changing"
        sort_rank = 3
    elif persistent:
        attention_tier = "persistent"
        attention_reason = "high-confidence class is stable"
        sort_rank = 2
    elif latest_class != "healthy":
        attention_tier = "monitor"
        attention_reason = "current non-healthy hypothesis"
        sort_rank = 1
    else:
        attention_tier = "stable"
        attention_reason = "current top hypothesis is healthy"
        sort_rank = 0

    return {
        "vehicleId": latest.vehicle_id,
        "experimentId": experiment_id,
        "runId": run_id,
        "latestClass": latest_class,
        "latestConfidence": round(float(latest.top_confidence), 6),
        "latestAnchorMileage": round(float(latest.anchor_mileage), 1),
        "firstClass": first.top_class,
        "firstAnchorMileage": round(float(first.anchor_mileage), 1),
        "classChanges": class_changes,
        "recentClassChanges": recent_class_changes,
        "recentStability": round(float(recent_stability), 6),
        "currentClassConfidenceSlopePer1kMiles": round(float(slope_per_1k), 8),
        "currentClassConfidenceDelta": round(float(confidence_delta), 8),
        "newlyEmerging": newly_emerging,
        "emergenceObserved": emergence_observed,
        "firstEmergenceClass": (
            first_emergence.top_class
            if first_emergence is not None
            else None
        ),
        "firstEmergenceMileage": (
            round(float(first_emergence.anchor_mileage), 1)
            if first_emergence is not None
            else None
        ),
        "milesSinceEmergence": (
            round(
                float(latest.anchor_mileage)
                - float(first_emergence.anchor_mileage),
                1,
            )
            if first_emergence is not None
            else None
        ),
        "historicalTransitions": class_changes > 0,
        "escalating": escalating,
        "deescalating": deescalating,
        "volatile": volatile,
        "persistent": persistent,
        "attentionTier": attention_tier,
        "attentionReason": attention_reason,
        "_sortRank": sort_rank,
    }


@router.get("/transitions")
def diagnostic_transitions(
    limit: int = Query(default=50, ge=1, le=200),
    min_confidence: float = Query(default=0.70, ge=0.0, le=1.0),
    db: Session = Depends(db_session),
) -> dict:
    """Summarize current-run changes in observable diagnostic hypotheses."""

    experiment_id, run = _require_current_run(db)

    rows = db.execute(
        select(DiagnosticReplayPoint)
        .where(DiagnosticReplayPoint.run_id == run.id)
        .order_by(
            DiagnosticReplayPoint.vehicle_id,
            DiagnosticReplayPoint.anchor_timestamp,
            DiagnosticReplayPoint.id,
        )
    ).scalars().all()

    grouped: dict[str, list[DiagnosticReplayPoint]] = {}
    for row in rows:
        grouped.setdefault(row.vehicle_id, []).append(row)

    records = []
    for vehicle_rows in grouped.values():
        record = _transition_record(
            vehicle_rows,
            experiment_id=experiment_id,
            run_id=run.id,
            incident_confidence=min_confidence,
        )
        if record is not None:
            records.append(record)

    records.sort(
        key=lambda item: (
            int(item["_sortRank"]),
            float(item["latestConfidence"]),
            float(item["recentStability"]),
            float(item["currentClassConfidenceSlopePer1kMiles"]),
        ),
        reverse=True,
    )

    summary = {
        "vehiclesAnalyzed": len(records),
        "currentNonHealthy": sum(
            1 for item in records if item["latestClass"] != "healthy"
        ),
        "newlyEmerging": sum(
            1 for item in records if item["newlyEmerging"]
        ),
        "emergenceObserved": sum(
            1 for item in records if item["emergenceObserved"]
        ),
        "historicalTransitions": sum(
            1 for item in records if item["historicalTransitions"]
        ),
        "escalating": sum(
            1 for item in records if item["escalating"]
        ),
        "deescalating": sum(
            1 for item in records if item["deescalating"]
        ),
        "recentTransitions": sum(
            1 for item in records if item["recentClassChanges"] > 0
        ),
        "volatile": sum(
            1 for item in records if item["volatile"]
        ),
        "persistent": sum(
            1 for item in records if item["persistent"]
        ),
    }

    public_records = []
    for item in records[:limit]:
        public_item = dict(item)
        public_item.pop("_sortRank", None)
        public_records.append(public_item)

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "champion": run.champion,
        "thresholds": {
            "recentWindowPoints": TRANSITION_RECENT_POINTS,
            "incidentConfidence": min_confidence,
            "escalationPer1kMiles": TRANSITION_ESCALATION_PER_1K_MILES,
            "stableFraction": TRANSITION_STABLE_FRACTION,
            "volatileFraction": TRANSITION_VOLATILE_FRACTION,
            "volatileClassChanges": TRANSITION_VOLATILE_CLASS_CHANGES,
        },
        "summary": summary,
        "vehicles": public_records,
        "scopePolicy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "sameLineageOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
        },
        "interpretationPolicy": (
            "Transition intelligence is derived only from current-run replayed "
            "model hypotheses over observable telemetry. Attention tiers are "
            "operational review heuristics, not calibrated failure risk, "
            "private failure truth, attribution, or causal proof."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _diagnostic_event_payload(row: DiagnosticEvent) -> dict:
    return {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "rulesVersion": row.rules_version,
        "vehicleId": row.vehicle_id,
        "eventType": row.event_type,
        "anchorTimestamp": row.anchor_timestamp.isoformat(),
        "anchorMileage": round(float(row.anchor_mileage), 1),
        "previousClass": row.previous_class,
        "currentClass": row.current_class,
        "previousConfidence": (
            round(float(row.previous_confidence), 6)
            if row.previous_confidence is not None
            else None
        ),
        "currentConfidence": (
            round(float(row.current_confidence), 6)
            if row.current_confidence is not None
            else None
        ),
        "confidenceDelta": (
            round(float(row.confidence_delta), 8)
            if row.confidence_delta is not None
            else None
        ),
        "slopePer1kMiles": (
            round(float(row.slope_per_1k_miles), 8)
            if row.slope_per_1k_miles is not None
            else None
        ),
        "observableEvidence": _json_list(row.evidence_json),
        "details": _json_object(row.details_json),
    }


@router.get("/events")
def diagnostic_events(
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(default=None),
    vehicle_id: str | None = Query(default=None),
    hypothesis_class: str | None = Query(default=None),
    min_confidence: float | None = Query(
        default=None,
        ge=0.0,
        le=1.0,
    ),
    db: Session = Depends(db_session),
) -> dict:
    """Return persisted replay-derived audit events for the current run."""

    experiment_id, run = _require_current_run(db)

    if (
        event_type is not None
        and event_type not in DIAGNOSTIC_EVENT_TYPES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported diagnostic event type",
                "allowed": list(DIAGNOSTIC_EVENT_TYPES),
            },
        )

    filters = [
        DiagnosticEvent.run_id == run.id,
        DiagnosticEvent.experiment_id == experiment_id,
    ]

    if event_type is not None:
        filters.append(DiagnosticEvent.event_type == event_type)
    if vehicle_id is not None:
        filters.append(DiagnosticEvent.vehicle_id == vehicle_id)
    if hypothesis_class is not None:
        filters.append(DiagnosticEvent.current_class == hypothesis_class)
    if min_confidence is not None:
        filters.append(
            DiagnosticEvent.current_confidence >= min_confidence
        )

    total_matched = int(
        db.scalar(
            select(func.count(DiagnosticEvent.id)).where(*filters)
        )
        or 0
    )

    rows = db.execute(
        select(DiagnosticEvent)
        .where(*filters)
        .order_by(
            desc(DiagnosticEvent.anchor_timestamp),
            desc(DiagnosticEvent.id),
        )
        .limit(limit)
    ).scalars().all()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "champion": run.champion,
        "totalMatched": total_matched,
        "returned": len(rows),
        "filters": {
            "eventType": event_type,
            "vehicleId": vehicle_id,
            "hypothesisClass": hypothesis_class,
            "minConfidence": min_confidence,
        },
        "events": [
            _diagnostic_event_payload(row)
            for row in rows
        ],
        "scopePolicy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "replayDerivedOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
        },
        "interpretationPolicy": (
            "Diagnostic events are deterministic state changes derived from "
            "persisted current-run replayed model hypotheses. They are not "
            "physical failure events, calibrated failure risk, private "
            "failure truth, attribution, or causal proof."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/events/summary")
def diagnostic_events_summary(
    db: Session = Depends(db_session),
) -> dict:
    """Summarize persisted replay-derived events for the current run."""

    experiment_id, run = _require_current_run(db)

    grouped = db.execute(
        select(
            DiagnosticEvent.event_type,
            func.count(DiagnosticEvent.id),
            func.count(func.distinct(DiagnosticEvent.vehicle_id)),
        )
        .where(
            DiagnosticEvent.run_id == run.id,
            DiagnosticEvent.experiment_id == experiment_id,
        )
        .group_by(DiagnosticEvent.event_type)
        .order_by(DiagnosticEvent.event_type)
    ).all()

    total_events = int(
        db.scalar(
            select(func.count(DiagnosticEvent.id)).where(
                DiagnosticEvent.run_id == run.id,
                DiagnosticEvent.experiment_id == experiment_id,
            )
        )
        or 0
    )
    vehicles_with_events = int(
        db.scalar(
            select(
                func.count(
                    func.distinct(DiagnosticEvent.vehicle_id)
                )
            ).where(
                DiagnosticEvent.run_id == run.id,
                DiagnosticEvent.experiment_id == experiment_id,
            )
        )
        or 0
    )
    rules_version = db.scalar(
        select(DiagnosticEvent.rules_version)
        .where(
            DiagnosticEvent.run_id == run.id,
            DiagnosticEvent.experiment_id == experiment_id,
        )
        .order_by(desc(DiagnosticEvent.id))
        .limit(1)
    )

    grouped_map = {
        event_type: {
            "events": int(event_count),
            "vehicles": int(vehicle_count),
        }
        for event_type, event_count, vehicle_count in grouped
    }

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "champion": run.champion,
        "rulesVersion": rules_version,
        "totalEvents": total_events,
        "vehiclesWithEvents": vehicles_with_events,
        "byType": [
            {
                "eventType": event_type,
                "events": grouped_map.get(
                    event_type,
                    {},
                ).get("events", 0),
                "vehicles": grouped_map.get(
                    event_type,
                    {},
                ).get("vehicles", 0),
            }
            for event_type in DIAGNOSTIC_EVENT_TYPES
        ],
        "scopePolicy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "replayDerivedOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _diagnostic_episode_payload(row: DiagnosticEpisode) -> dict:
    return {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "rulesVersion": row.rules_version,
        "sourceEventRulesVersion": row.source_event_rules_version,
        "vehicleId": row.vehicle_id,
        "hypothesisClass": row.hypothesis_class,
        "state": row.state,
        "startReason": row.start_reason,
        "startTimestamp": row.start_timestamp.isoformat(),
        "startMileage": round(float(row.start_mileage), 1),
        "endTimestamp": row.end_timestamp.isoformat(),
        "endMileage": round(float(row.end_mileage), 1),
        "observedSpanMiles": round(
            max(0.0, float(row.end_mileage) - float(row.start_mileage)),
            1,
        ),
        "isOpen": bool(row.is_open),
        "leftCensored": bool(row.left_censored),
        "eventCount": int(row.event_count),
        "escalationCount": int(row.escalation_count),
        "deescalationCount": int(row.deescalation_count),
        "classChangeCount": int(row.class_change_count),
        "stabilizedCount": int(row.stabilized_count),
        "destabilizedCount": int(row.destabilized_count),
        "peakConfidence": (
            round(float(row.peak_confidence), 6)
            if row.peak_confidence is not None
            else None
        ),
        "latestConfidence": (
            round(float(row.latest_confidence), 6)
            if row.latest_confidence is not None
            else None
        ),
        "eventIds": _json_list(row.event_ids_json),
        "details": _json_object(row.details_json),
    }


@router.get("/episodes")
def diagnostic_episodes(
    limit: int = Query(default=100, ge=1, le=500),
    state: str | None = Query(default=None),
    vehicle_id: str | None = Query(default=None),
    hypothesis_class: str | None = Query(default=None),
    open_only: bool | None = Query(default=None),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)

    if state is not None and state not in DIAGNOSTIC_EPISODE_STATES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported diagnostic episode state",
                "allowed": list(DIAGNOSTIC_EPISODE_STATES),
            },
        )

    filters = [
        DiagnosticEpisode.run_id == run.id,
        DiagnosticEpisode.experiment_id == experiment_id,
    ]

    if state is not None:
        filters.append(DiagnosticEpisode.state == state)
    if vehicle_id is not None:
        filters.append(DiagnosticEpisode.vehicle_id == vehicle_id)
    if hypothesis_class is not None:
        filters.append(DiagnosticEpisode.hypothesis_class == hypothesis_class)
    if open_only is not None:
        filters.append(DiagnosticEpisode.is_open == open_only)

    total_matched = int(
        db.scalar(select(func.count(DiagnosticEpisode.id)).where(*filters))
        or 0
    )

    rows = db.execute(
        select(DiagnosticEpisode)
        .where(*filters)
        .order_by(
            desc(DiagnosticEpisode.start_timestamp),
            desc(DiagnosticEpisode.id),
        )
        .limit(limit)
    ).scalars().all()

    source_rules_version = db.scalar(
        select(DiagnosticEpisode.source_event_rules_version)
        .where(
            DiagnosticEpisode.run_id == run.id,
            DiagnosticEpisode.experiment_id == experiment_id,
        )
        .order_by(desc(DiagnosticEpisode.id))
        .limit(1)
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "champion": run.champion,
        "totalMatched": total_matched,
        "returned": len(rows),
        "eventsSourceRequired": source_rules_version,
        "filters": {
            "state": state,
            "vehicleId": vehicle_id,
            "hypothesisClass": hypothesis_class,
            "openOnly": open_only,
        },
        "episodes": [_diagnostic_episode_payload(row) for row in rows],
        "scopePolicy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "eventDerivedOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
        },
        "interpretationPolicy": (
            "Diagnostic episodes group persisted current-run diagnostic "
            "events for one non-healthy model hypothesis. Episode spans are "
            "observed model-event spans, not physical degradation or failure "
            "intervals, calibrated failure risk, attribution, or causal proof."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/episodes/summary")
def diagnostic_episodes_summary(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)

    base_filters = (
        DiagnosticEpisode.run_id == run.id,
        DiagnosticEpisode.experiment_id == experiment_id,
    )

    total_episodes = int(
        db.scalar(select(func.count(DiagnosticEpisode.id)).where(*base_filters))
        or 0
    )
    vehicles_with_episodes = int(
        db.scalar(
            select(
                func.count(func.distinct(DiagnosticEpisode.vehicle_id))
            ).where(*base_filters)
        )
        or 0
    )
    open_episodes = int(
        db.scalar(
            select(func.count(DiagnosticEpisode.id)).where(
                *base_filters,
                DiagnosticEpisode.is_open.is_(True),
            )
        )
        or 0
    )
    left_censored_episodes = int(
        db.scalar(
            select(func.count(DiagnosticEpisode.id)).where(
                *base_filters,
                DiagnosticEpisode.left_censored.is_(True),
            )
        )
        or 0
    )

    state_rows = db.execute(
        select(
            DiagnosticEpisode.state,
            func.count(DiagnosticEpisode.id),
            func.count(func.distinct(DiagnosticEpisode.vehicle_id)),
        )
        .where(*base_filters)
        .group_by(DiagnosticEpisode.state)
        .order_by(DiagnosticEpisode.state)
    ).all()

    class_rows = db.execute(
        select(
            DiagnosticEpisode.hypothesis_class,
            func.count(DiagnosticEpisode.id),
            func.count(func.distinct(DiagnosticEpisode.vehicle_id)),
        )
        .where(*base_filters)
        .group_by(DiagnosticEpisode.hypothesis_class)
        .order_by(DiagnosticEpisode.hypothesis_class)
    ).all()

    state_map = {
        episode_state: {
            "episodes": int(count),
            "vehicles": int(vehicles),
        }
        for episode_state, count, vehicles in state_rows
    }

    rules_version = db.scalar(
        select(DiagnosticEpisode.rules_version)
        .where(*base_filters)
        .order_by(desc(DiagnosticEpisode.id))
        .limit(1)
    )
    source_event_rules_version = db.scalar(
        select(DiagnosticEpisode.source_event_rules_version)
        .where(*base_filters)
        .order_by(desc(DiagnosticEpisode.id))
        .limit(1)
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "champion": run.champion,
        "rulesVersion": rules_version,
        "sourceEventRulesVersion": source_event_rules_version,
        "totalEpisodes": total_episodes,
        "vehiclesWithEpisodes": vehicles_with_episodes,
        "openEpisodes": open_episodes,
        "closedEpisodes": total_episodes - open_episodes,
        "leftCensoredEpisodes": left_censored_episodes,
        "byState": [
            {
                "state": episode_state,
                "episodes": state_map.get(episode_state, {}).get("episodes", 0),
                "vehicles": state_map.get(episode_state, {}).get("vehicles", 0),
            }
            for episode_state in DIAGNOSTIC_EPISODE_STATES
        ],
        "byClass": [
            {
                "hypothesisClass": hypothesis_class,
                "episodes": int(count),
                "vehicles": int(vehicles),
            }
            for hypothesis_class, count, vehicles in class_rows
        ],
        "scopePolicy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "eventDerivedOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }



class DiagnosticCaseUpdate(BaseModel):
    status: str | None = None
    review_priority: str | None = None
    assigned_to: str | None = Field(default=None, max_length=64)
    clear_assignment: bool = False
    actor: str = Field(default="operator", min_length=1, max_length=64)


class DiagnosticCaseNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    actor: str = Field(default="operator", min_length=1, max_length=64)


def _diagnostic_case_payload(row: DiagnosticCase) -> dict:
    return {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "episodeId": row.episode_id,
        "rulesVersion": row.rules_version,
        "sourceEpisodeRulesVersion": row.source_episode_rules_version,
        "sourceEventRulesVersion": row.source_event_rules_version,
        "vehicleId": row.vehicle_id,
        "hypothesisClass": row.hypothesis_class,
        "episodeStateAtCreation": row.episode_state_at_creation,
        "status": row.status,
        "reviewPriority": row.review_priority,
        "assignedTo": row.assigned_to,
        "title": row.title,
        "startTimestamp": row.start_timestamp.isoformat(),
        "startMileage": round(float(row.start_mileage), 1),
        "latestTimestamp": row.latest_timestamp.isoformat(),
        "latestMileage": round(float(row.latest_mileage), 1),
        "observedSpanMiles": round(
            max(0.0, float(row.latest_mileage) - float(row.start_mileage)),
            1,
        ),
        "latestConfidence": (
            round(float(row.latest_confidence), 6)
            if row.latest_confidence is not None
            else None
        ),
        "peakConfidence": (
            round(float(row.peak_confidence), 6)
            if row.peak_confidence is not None
            else None
        ),
        "eventCount": int(row.event_count),
        "leftCensored": bool(row.left_censored),
        "noteCount": int(row.note_count),
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
        "lastActivityAt": row.last_activity_at.isoformat(),
        "details": _json_object(row.details_json),
    }


def _diagnostic_case_activity_payload(
    row: DiagnosticCaseActivity,
) -> dict:
    return {
        "id": row.id,
        "caseId": row.case_id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "vehicleId": row.vehicle_id,
        "createdAt": row.created_at.isoformat(),
        "activityType": row.activity_type,
        "actor": row.actor,
        "fromValue": row.from_value,
        "toValue": row.to_value,
        "note": row.note_text,
        "details": _json_object(row.details_json),
    }


def _require_current_case(
    case_id: int,
    db: Session,
) -> tuple[str, DiagnosticModelRun, DiagnosticCase]:
    experiment_id, run = _require_current_run(db)
    row = db.execute(
        select(DiagnosticCase)
        .where(
            DiagnosticCase.id == case_id,
            DiagnosticCase.run_id == run.id,
            DiagnosticCase.experiment_id == experiment_id,
        )
        .limit(1)
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Diagnostic case not found in the current run",
        )

    return experiment_id, run, row


@router.get("/cases")
def diagnostic_cases(
    limit: int = Query(default=100, ge=1, le=500),
    status: str | None = Query(default=None),
    review_priority: str | None = Query(default=None),
    vehicle_id: str | None = Query(default=None),
    hypothesis_class: str | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
    unassigned_only: bool = Query(default=False),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)

    if status is not None and status not in DIAGNOSTIC_CASE_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported diagnostic case status",
                "allowed": list(DIAGNOSTIC_CASE_STATUSES),
            },
        )
    if (
        review_priority is not None
        and review_priority not in DIAGNOSTIC_CASE_PRIORITIES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported diagnostic case priority",
                "allowed": list(DIAGNOSTIC_CASE_PRIORITIES),
            },
        )

    filters = [
        DiagnosticCase.run_id == run.id,
        DiagnosticCase.experiment_id == experiment_id,
    ]

    if status is not None:
        filters.append(DiagnosticCase.status == status)
    if review_priority is not None:
        filters.append(
            DiagnosticCase.review_priority == review_priority
        )
    if vehicle_id is not None:
        filters.append(DiagnosticCase.vehicle_id == vehicle_id)
    if hypothesis_class is not None:
        filters.append(
            DiagnosticCase.hypothesis_class == hypothesis_class
        )
    if assigned_to is not None:
        filters.append(DiagnosticCase.assigned_to == assigned_to)
    if unassigned_only:
        filters.append(DiagnosticCase.assigned_to.is_(None))

    total_matched = int(
        db.scalar(select(func.count(DiagnosticCase.id)).where(*filters))
        or 0
    )
    rows = db.execute(
        select(DiagnosticCase)
        .where(*filters)
        .order_by(
            desc(DiagnosticCase.last_activity_at),
            desc(DiagnosticCase.updated_at),
            desc(DiagnosticCase.id),
        )
        .limit(limit)
    ).scalars().all()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "champion": run.champion,
        "totalMatched": total_matched,
        "returned": len(rows),
        "filters": {
            "status": status,
            "reviewPriority": review_priority,
            "vehicleId": vehicle_id,
            "hypothesisClass": hypothesis_class,
            "assignedTo": assigned_to,
            "unassignedOnly": unassigned_only,
        },
        "cases": [_diagnostic_case_payload(row) for row in rows],
        "scopePolicy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "episodeDerivedSource": True,
            "workflowMetadataSeparate": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
        },
        "interpretationPolicy": (
            "Cases organize persisted model-hypothesis episodes for "
            "operational review. Review priority and operator workflow "
            "metadata are not calibrated physical-failure risk, private "
            "failure truth, attribution, or causal proof."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/cases/summary")
def diagnostic_cases_summary(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    base_filters = (
        DiagnosticCase.run_id == run.id,
        DiagnosticCase.experiment_id == experiment_id,
    )

    total_cases = int(
        db.scalar(select(func.count(DiagnosticCase.id)).where(*base_filters))
        or 0
    )
    closed_cases = int(
        db.scalar(
            select(func.count(DiagnosticCase.id)).where(
                *base_filters,
                DiagnosticCase.status == CASE_CLOSED,
            )
        )
        or 0
    )
    unassigned_cases = int(
        db.scalar(
            select(func.count(DiagnosticCase.id)).where(
                *base_filters,
                DiagnosticCase.assigned_to.is_(None),
                DiagnosticCase.status != CASE_CLOSED,
            )
        )
        or 0
    )

    status_rows = db.execute(
        select(
            DiagnosticCase.status,
            func.count(DiagnosticCase.id),
        )
        .where(*base_filters)
        .group_by(DiagnosticCase.status)
    ).all()
    priority_rows = db.execute(
        select(
            DiagnosticCase.review_priority,
            func.count(DiagnosticCase.id),
        )
        .where(*base_filters)
        .group_by(DiagnosticCase.review_priority)
    ).all()
    class_rows = db.execute(
        select(
            DiagnosticCase.hypothesis_class,
            func.count(DiagnosticCase.id),
        )
        .where(*base_filters)
        .group_by(DiagnosticCase.hypothesis_class)
        .order_by(DiagnosticCase.hypothesis_class)
    ).all()

    status_map = {
        str(case_status): int(count)
        for case_status, count in status_rows
    }
    priority_map = {
        str(priority): int(count)
        for priority, count in priority_rows
    }

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "champion": run.champion,
        "totalCases": total_cases,
        "activeCases": total_cases - closed_cases,
        "closedCases": closed_cases,
        "unassignedCases": unassigned_cases,
        "byStatus": [
            {
                "status": value,
                "cases": status_map.get(value, 0),
            }
            for value in DIAGNOSTIC_CASE_STATUSES
        ],
        "byPriority": [
            {
                "reviewPriority": value,
                "cases": priority_map.get(value, 0),
            }
            for value in DIAGNOSTIC_CASE_PRIORITIES
        ],
        "byClass": [
            {
                "hypothesisClass": hypothesis_class,
                "cases": int(count),
            }
            for hypothesis_class, count in class_rows
        ],
        "scopePolicy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/cases/{case_id}")
def diagnostic_case_detail(
    case_id: int,
    activity_limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, case = _require_current_case(case_id, db)

    activities = db.execute(
        select(DiagnosticCaseActivity)
        .where(
            DiagnosticCaseActivity.case_id == case.id,
            DiagnosticCaseActivity.run_id == run.id,
            DiagnosticCaseActivity.experiment_id == experiment_id,
        )
        .order_by(
            desc(DiagnosticCaseActivity.created_at),
            desc(DiagnosticCaseActivity.id),
        )
        .limit(activity_limit)
    ).scalars().all()

    return {
        "case": _diagnostic_case_payload(case),
        "activities": [
            _diagnostic_case_activity_payload(row)
            for row in activities
        ],
        "interpretationPolicy": (
            "The source episode remains diagnostic model evidence. "
            "Activities are operator workflow metadata and do not rewrite "
            "the source episode, events, replay, model, or benchmark."
        ),
    }


@router.patch("/cases/{case_id}")
def update_diagnostic_case(
    case_id: int,
    update: DiagnosticCaseUpdate,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, case = _require_current_case(case_id, db)
    now = datetime.now(timezone.utc)
    activities: list[DiagnosticCaseActivity] = []

    if update.status is not None:
        if update.status not in DIAGNOSTIC_CASE_STATUSES:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Unsupported diagnostic case status",
                    "allowed": list(DIAGNOSTIC_CASE_STATUSES),
                },
            )
        if update.status != case.status:
            activities.append(
                DiagnosticCaseActivity(
                    case_id=case.id,
                    run_id=run.id,
                    experiment_id=experiment_id,
                    vehicle_id=case.vehicle_id,
                    created_at=now,
                    activity_type=CASE_ACTIVITY_STATUS_CHANGED,
                    actor=update.actor,
                    from_value=case.status,
                    to_value=update.status,
                    note_text=None,
                    details_json="{}",
                )
            )
            case.status = update.status

    if update.review_priority is not None:
        if (
            update.review_priority
            not in DIAGNOSTIC_CASE_PRIORITIES
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Unsupported diagnostic case priority",
                    "allowed": list(DIAGNOSTIC_CASE_PRIORITIES),
                },
            )
        if update.review_priority != case.review_priority:
            activities.append(
                DiagnosticCaseActivity(
                    case_id=case.id,
                    run_id=run.id,
                    experiment_id=experiment_id,
                    vehicle_id=case.vehicle_id,
                    created_at=now,
                    activity_type=CASE_ACTIVITY_PRIORITY_CHANGED,
                    actor=update.actor,
                    from_value=case.review_priority,
                    to_value=update.review_priority,
                    note_text=None,
                    details_json="{}",
                )
            )
            case.review_priority = update.review_priority

    target_assignment = case.assigned_to
    assignment_requested = False
    if update.clear_assignment:
        target_assignment = None
        assignment_requested = True
    elif update.assigned_to is not None:
        value = update.assigned_to.strip()
        target_assignment = value or None
        assignment_requested = True

    if assignment_requested and target_assignment != case.assigned_to:
        activities.append(
            DiagnosticCaseActivity(
                case_id=case.id,
                run_id=run.id,
                experiment_id=experiment_id,
                vehicle_id=case.vehicle_id,
                created_at=now,
                activity_type=CASE_ACTIVITY_ASSIGNED,
                actor=update.actor,
                from_value=case.assigned_to,
                to_value=target_assignment,
                note_text=None,
                details_json="{}",
            )
        )
        case.assigned_to = target_assignment

    if activities:
        case.updated_at = now
        case.last_activity_at = now
        for activity in activities:
            db.add(activity)
        db.add(case)
        db.commit()
        db.refresh(case)

    return _diagnostic_case_payload(case)


@router.post("/cases/{case_id}/notes")
def add_diagnostic_case_note(
    case_id: int,
    request: DiagnosticCaseNoteCreate,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, case = _require_current_case(case_id, db)
    note = request.note.strip()
    if not note:
        raise HTTPException(
            status_code=422,
            detail="Diagnostic case note cannot be blank",
        )

    now = datetime.now(timezone.utc)
    activity = DiagnosticCaseActivity(
        case_id=case.id,
        run_id=run.id,
        experiment_id=experiment_id,
        vehicle_id=case.vehicle_id,
        created_at=now,
        activity_type=CASE_ACTIVITY_NOTE_ADDED,
        actor=request.actor,
        from_value=None,
        to_value=None,
        note_text=note,
        details_json="{}",
    )

    case.note_count += 1
    case.updated_at = now
    case.last_activity_at = now
    db.add(activity)
    db.add(case)
    db.commit()
    db.refresh(activity)

    return _diagnostic_case_activity_payload(activity)




class DiagnosticWatchlistCreate(BaseModel):
    actor: str = Field(default="operator", min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=1000)


class DiagnosticInvestigationViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=96)
    filters: dict = Field(default_factory=dict)
    actor: str = Field(default="operator", min_length=1, max_length=64)


def _latest_case_context_map(
    db: Session,
    *,
    experiment_id: str,
    cases: list[DiagnosticCase],
) -> dict[str, dict]:
    vehicle_ids = sorted({row.vehicle_id for row in cases})
    if not vehicle_ids:
        return {}

    latest = (
        select(
            Telemetry.vehicle_id,
            func.max(Telemetry.id).label("max_id"),
        )
        .where(
            Telemetry.experiment_id == experiment_id,
            Telemetry.vehicle_id.in_(vehicle_ids),
        )
        .group_by(Telemetry.vehicle_id)
        .subquery()
    )
    rows = db.execute(
        select(Telemetry).join(
            latest,
            Telemetry.id == latest.c.max_id,
        )
    ).scalars().all()

    return {
        row.vehicle_id: {
            "model": row.model,
            "factory": row.factory,
            "firmware": row.firmware,
            "pumpRevision": row.pump_revision,
            "mileage": round(float(row.mileage), 1),
        }
        for row in rows
    }


def _pattern_case_record(
    row: DiagnosticCase,
    context: dict | None,
) -> dict:
    context = context or {}
    return {
        "caseId": row.id,
        "episodeId": row.episode_id,
        "vehicleId": row.vehicle_id,
        "hypothesisClass": row.hypothesis_class,
        "reviewPriority": row.review_priority,
        "status": row.status,
        "episodeState": row.episode_state_at_creation,
        "latestConfidence": (
            round(float(row.latest_confidence), 6)
            if row.latest_confidence is not None
            else None
        ),
        "eventCount": int(row.event_count),
        "model": context.get("model"),
        "factory": context.get("factory"),
        "firmware": context.get("firmware"),
        "pumpRevision": context.get("pumpRevision"),
        "currentMileage": context.get("mileage"),
    }


def _current_pattern_records(
    db: Session,
) -> tuple[str, DiagnosticModelRun, list[dict]]:
    experiment_id, run = _require_current_run(db)
    cases = db.execute(
        select(DiagnosticCase)
        .where(
            DiagnosticCase.run_id == run.id,
            DiagnosticCase.experiment_id == experiment_id,
        )
        .order_by(DiagnosticCase.id)
    ).scalars().all()
    contexts = _latest_case_context_map(
        db,
        experiment_id=experiment_id,
        cases=cases,
    )
    records = [
        _pattern_case_record(row, contexts.get(row.vehicle_id))
        for row in cases
    ]
    return experiment_id, run, records


def _dimension_rows(
    records: list[dict],
    key: str,
) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in records:
        value = row.get(key)
        if value is None:
            continue
        grouped.setdefault(str(value), []).append(row)

    result = []
    for value, rows in grouped.items():
        confidences = [
            float(row["latestConfidence"])
            for row in rows
            if row.get("latestConfidence") is not None
        ]
        result.append(
            {
                "value": value,
                "cases": len(rows),
                "vehicles": len(
                    {str(row["vehicleId"]) for row in rows}
                ),
                "highPriorityCases": sum(
                    1
                    for row in rows
                    if row.get("reviewPriority") == "HIGH"
                ),
                "activeCases": sum(
                    1
                    for row in rows
                    if row.get("status") != CASE_CLOSED
                ),
                "averageLatestConfidence": (
                    round(sum(confidences) / len(confidences), 6)
                    if confidences
                    else None
                ),
            }
        )

    result.sort(
        key=lambda item: (
            int(item["cases"]),
            int(item["highPriorityCases"]),
            float(item["averageLatestConfidence"] or 0.0),
        ),
        reverse=True,
    )
    return result


@router.get("/patterns/overview")
def diagnostic_pattern_overview(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_pattern_records(db)

    dimensions = {
        dimension: _dimension_rows(records, dimension)
        for dimension in PATTERN_DIMENSIONS
    }

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": PATTERN_RULES_VERSION,
        "totalCases": len(records),
        "casesWithTelemetryContext": sum(
            1 for row in records if row.get("firmware") is not None
        ),
        "dimensions": dimensions,
        "topHotspots": [
            {
                "dimension": dimension,
                **rows[0],
            }
            for dimension, rows in dimensions.items()
            if rows
        ],
        "scopePolicy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "caseDerived": True,
            "observableTelemetryContextOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
        },
        "interpretationPolicy": (
            "Pattern counts are descriptive groupings of current-run "
            "diagnostic cases and exact-experiment observable vehicle "
            "context. Concentration is not enrichment, attribution, "
            "physical-failure risk, or causal proof."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/patterns/clusters")
def diagnostic_pattern_clusters(
    min_cases: int = Query(
        default=DEFAULT_CLUSTER_MIN_CASES,
        ge=1,
        le=100,
    ),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_pattern_records(db)

    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for row in records:
        key = (
            str(row.get("hypothesisClass") or "unknown"),
            str(row.get("firmware") or "unknown"),
            str(row.get("factory") or "unknown"),
        )
        grouped.setdefault(key, []).append(row)

    clusters = []
    for (
        hypothesis_class,
        firmware,
        factory,
    ), rows in grouped.items():
        if len(rows) < min_cases:
            continue
        confidences = [
            float(row["latestConfidence"])
            for row in rows
            if row.get("latestConfidence") is not None
        ]
        clusters.append(
            {
                "clusterKey": (
                    f"{hypothesis_class}|{firmware}|{factory}"
                ),
                "hypothesisClass": hypothesis_class,
                "firmware": firmware,
                "factory": factory,
                "cases": len(rows),
                "vehicles": len(
                    {str(row["vehicleId"]) for row in rows}
                ),
                "highPriorityCases": sum(
                    1
                    for row in rows
                    if row.get("reviewPriority") == "HIGH"
                ),
                "averageLatestConfidence": (
                    round(sum(confidences) / len(confidences), 6)
                    if confidences
                    else None
                ),
                "pumpRevisions": sorted(
                    {
                        str(row["pumpRevision"])
                        for row in rows
                        if row.get("pumpRevision") is not None
                    }
                ),
                "models": sorted(
                    {
                        str(row["model"])
                        for row in rows
                        if row.get("model") is not None
                    }
                ),
                "caseIds": [
                    int(row["caseId"])
                    for row in rows[:MAX_CLUSTER_CASE_IDS]
                ],
                "vehicleIds": [
                    str(row["vehicleId"])
                    for row in rows[:MAX_CLUSTER_CASE_IDS]
                ],
            }
        )

    clusters.sort(
        key=lambda item: (
            int(item["cases"]),
            int(item["highPriorityCases"]),
            float(item["averageLatestConfidence"] or 0.0),
        ),
        reverse=True,
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": PATTERN_RULES_VERSION,
        "minCases": min_cases,
        "totalClusters": len(clusters),
        "returned": min(limit, len(clusters)),
        "clusters": clusters[:limit],
        "interpretationPolicy": (
            "Clusters are deterministic descriptive groups defined by "
            "hypothesis class, firmware and factory. They are investigation "
            "shortcuts, not learned latent clusters or causal findings."
        ),
    }


@router.get("/patterns/similar/{case_id}")
def similar_diagnostic_cases(
    case_id: int,
    limit: int = Query(default=12, ge=1, le=100),
    min_score: float = Query(default=0.20, ge=0.0, le=1.0),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, case = _require_current_case(case_id, db)
    _, _, records = _current_pattern_records(db)

    target = next(
        (row for row in records if row["caseId"] == case.id),
        None,
    )
    if target is None:
        raise HTTPException(
            status_code=404,
            detail="Pattern record unavailable for current case",
        )

    similar = []
    for candidate in records:
        if candidate["caseId"] == case.id:
            continue
        score, matched = similarity_score(target, candidate)
        if score < min_score:
            continue
        similar.append(
            {
                **candidate,
                "similarityScore": score,
                "matchedDimensions": matched,
            }
        )

    similar.sort(
        key=lambda item: (
            float(item["similarityScore"]),
            float(item.get("latestConfidence") or 0.0),
        ),
        reverse=True,
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": PATTERN_RULES_VERSION,
        "target": target,
        "returned": min(limit, len(similar)),
        "similarCases": similar[:limit],
        "interpretationPolicy": (
            "Similarity is a deterministic metadata/context matching "
            "heuristic. It is not a learned probability of shared failure "
            "mode, attribution, or causal proof."
        ),
    }


def _watchlist_payload(row: DiagnosticWatchlistEntry) -> dict:
    return {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "caseId": row.case_id,
        "vehicleId": row.vehicle_id,
        "createdAt": row.created_at.isoformat(),
        "actor": row.actor,
        "note": row.note,
    }


@router.get("/watchlist")
def diagnostic_watchlist(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    rows = db.execute(
        select(DiagnosticWatchlistEntry)
        .where(
            DiagnosticWatchlistEntry.run_id == run.id,
            DiagnosticWatchlistEntry.experiment_id == experiment_id,
        )
        .order_by(
            desc(DiagnosticWatchlistEntry.created_at),
            desc(DiagnosticWatchlistEntry.id),
        )
    ).scalars().all()

    case_ids = [row.case_id for row in rows]
    cases = (
        db.execute(
            select(DiagnosticCase).where(
                DiagnosticCase.run_id == run.id,
                DiagnosticCase.id.in_(case_ids),
            )
        ).scalars().all()
        if case_ids
        else []
    )
    case_map = {row.id: row for row in cases}

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "entries": [
            {
                **_watchlist_payload(row),
                "case": (
                    _diagnostic_case_payload(case_map[row.case_id])
                    if row.case_id in case_map
                    else None
                ),
            }
            for row in rows
        ],
        "total": len(rows),
    }


@router.post("/watchlist/{case_id}")
def add_diagnostic_watchlist_entry(
    case_id: int,
    request: DiagnosticWatchlistCreate,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, case = _require_current_case(case_id, db)

    existing = db.execute(
        select(DiagnosticWatchlistEntry)
        .where(
            DiagnosticWatchlistEntry.run_id == run.id,
            DiagnosticWatchlistEntry.case_id == case.id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return _watchlist_payload(existing)

    row = DiagnosticWatchlistEntry(
        run_id=run.id,
        experiment_id=experiment_id,
        case_id=case.id,
        vehicle_id=case.vehicle_id,
        created_at=datetime.now(timezone.utc),
        actor=request.actor,
        note=(request.note.strip() if request.note else None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _watchlist_payload(row)


@router.delete("/watchlist/{case_id}")
def remove_diagnostic_watchlist_entry(
    case_id: int,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, case = _require_current_case(case_id, db)
    row = db.execute(
        select(DiagnosticWatchlistEntry)
        .where(
            DiagnosticWatchlistEntry.run_id == run.id,
            DiagnosticWatchlistEntry.experiment_id == experiment_id,
            DiagnosticWatchlistEntry.case_id == case.id,
        )
        .limit(1)
    ).scalar_one_or_none()

    if row is None:
        return {"removed": False, "caseId": case.id}

    db.delete(row)
    db.commit()
    return {"removed": True, "caseId": case.id}


def _investigation_view_payload(
    row: DiagnosticInvestigationView,
) -> dict:
    return {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "name": row.name,
        "actor": row.actor,
        "filters": _json_object(row.filters_json),
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
    }


@router.get("/investigation-views")
def diagnostic_investigation_views(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    rows = db.execute(
        select(DiagnosticInvestigationView)
        .where(
            DiagnosticInvestigationView.run_id == run.id,
            DiagnosticInvestigationView.experiment_id == experiment_id,
        )
        .order_by(
            desc(DiagnosticInvestigationView.updated_at),
            DiagnosticInvestigationView.name,
        )
    ).scalars().all()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "views": [
            _investigation_view_payload(row)
            for row in rows
        ],
        "total": len(rows),
    }


@router.post("/investigation-views")
def create_diagnostic_investigation_view(
    request: DiagnosticInvestigationViewCreate,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    name = request.name.strip()
    if not name:
        raise HTTPException(
            status_code=422,
            detail="Investigation view name cannot be blank",
        )

    allowed_filter_keys = {
        "status",
        "reviewPriority",
        "hypothesisClass",
        "unassignedOnly",
    }
    unsupported = sorted(
        set(request.filters) - allowed_filter_keys
    )
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported investigation view filters",
                "unsupported": unsupported,
                "allowed": sorted(allowed_filter_keys),
            },
        )

    existing = db.execute(
        select(DiagnosticInvestigationView)
        .where(
            DiagnosticInvestigationView.run_id == run.id,
            DiagnosticInvestigationView.name == name,
        )
        .limit(1)
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing is None:
        row = DiagnosticInvestigationView(
            run_id=run.id,
            experiment_id=experiment_id,
            created_at=now,
            updated_at=now,
            actor=request.actor,
            name=name,
            filters_json=json.dumps(
                request.filters,
                sort_keys=True,
            ),
        )
        db.add(row)
    else:
        row = existing
        row.updated_at = now
        row.actor = request.actor
        row.filters_json = json.dumps(
            request.filters,
            sort_keys=True,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return _investigation_view_payload(row)


@router.delete("/investigation-views/{view_id}")
def delete_diagnostic_investigation_view(
    view_id: int,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    row = db.execute(
        select(DiagnosticInvestigationView)
        .where(
            DiagnosticInvestigationView.id == view_id,
            DiagnosticInvestigationView.run_id == run.id,
            DiagnosticInvestigationView.experiment_id == experiment_id,
        )
        .limit(1)
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Investigation view not found in current run",
        )

    db.delete(row)
    db.commit()
    return {"deleted": True, "viewId": view_id}




class DiagnosticMaintenancePlanUpdate(BaseModel):
    state: str | None = None
    owner: str | None = Field(default=None, max_length=64)
    clear_owner: bool = False
    target_mileage: float | None = Field(default=None, ge=0.0)
    clear_target_mileage: bool = False
    note: str | None = Field(default=None, max_length=2000)
    actor: str = Field(default="operator", min_length=1, max_length=64)


def _hypothesis_confidence(
    point: DiagnosticReplayPoint,
    hypothesis_class: str,
) -> float | None:
    for item in _json_list(point.hypotheses_json):
        if not isinstance(item, dict):
            continue
        if item.get("class") != hypothesis_class:
            continue
        value = item.get("confidence")
        if isinstance(value, (int, float)):
            return float(value)

    if point.top_class == hypothesis_class:
        return float(point.top_confidence)
    return None


def _trajectory_payload(
    case: DiagnosticCase,
    points: list[DiagnosticReplayPoint],
    *,
    watchlisted: bool,
    plan: DiagnosticMaintenancePlan | None,
) -> dict:
    trajectory = []
    for point in points:
        # Operational prognostics are constrained to the persisted
        # diagnostic-case evidence window. Run-frozen replay anchors before
        # the episode begins or after its latest evidence must not influence
        # the current case trajectory. Later replay remains available only to
        # the explicitly historical backtest endpoint.
        if (
            float(point.anchor_mileage) < float(case.start_mileage)
            or float(point.anchor_mileage) > float(case.latest_mileage)
        ):
            continue

        confidence = _hypothesis_confidence(
            point,
            case.hypothesis_class,
        )
        if confidence is None:
            continue
        trajectory.append(
            {
                "timestamp": point.anchor_timestamp.isoformat(),
                "mileage": round(float(point.anchor_mileage), 1),
                "confidence": round(float(confidence), 6),
            }
        )

    fit = fit_trajectory(
        [
            (item["mileage"], item["confidence"])
            for item in trajectory[-FIT_WINDOW_POINTS:]
        ]
    )

    horizon = None
    if fit is not None:
        horizon = estimate_threshold_horizon(
            latest_confidence=fit["latestConfidence"],
            slope_per_1k_miles=fit["slopePer1kMiles"],
            slope_std_error_per_1k_miles=fit[
                "slopeStdErrorPer1kMiles"
            ],
        )

    priority = maintenance_priority(
        review_priority=case.review_priority,
        episode_state=case.episode_state_at_creation,
        latest_confidence=(
            fit["latestConfidence"]
            if fit is not None
            else case.latest_confidence
        ),
        slope_per_1k_miles=(
            fit["slopePer1kMiles"]
            if fit is not None
            else None
        ),
        estimated_miles_to_threshold=(
            horizon["estimatedMilesToThreshold"]
            if horizon is not None
            else None
        ),
        watchlisted=watchlisted,
    )

    return {
        "caseId": case.id,
        "episodeId": case.episode_id,
        "vehicleId": case.vehicle_id,
        "hypothesisClass": case.hypothesis_class,
        "caseStatus": case.status,
        "reviewPriority": case.review_priority,
        "episodeState": case.episode_state_at_creation,
        "watchlisted": watchlisted,
        "trajectoryEligible": len(trajectory) >= MIN_TRAJECTORY_POINTS,
        "trajectoryPointCount": len(trajectory),
        "trajectory": trajectory,
        "fit": (
            {
                key: (
                    round(float(value), 6)
                    if isinstance(value, float)
                    else value
                )
                for key, value in fit.items()
            }
            if fit is not None
            else None
        ),
        "experimentalHorizon": (
            {
                key: (
                    round(float(value), 1)
                    if isinstance(value, float)
                    else value
                )
                for key, value in horizon.items()
            }
            if horizon is not None
            else None
        ),
        **priority,
        "maintenancePlan": (
            _maintenance_plan_payload(plan)
            if plan is not None
            else None
        ),
    }


def _current_prognostic_records(
    db: Session,
    *,
    selected_run: DiagnosticModelRun | None = None,
) -> tuple[str, DiagnosticModelRun, list[dict]]:
    if selected_run is None:
        experiment_id, run = _require_current_run(db)
    else:
        run = selected_run
        experiment_id = run.experiment_id

    cases = db.execute(
        select(DiagnosticCase)
        .where(
            DiagnosticCase.run_id == run.id,
            DiagnosticCase.experiment_id == experiment_id,
        )
        .order_by(DiagnosticCase.id)
    ).scalars().all()

    vehicle_ids = sorted({row.vehicle_id for row in cases})
    replay_rows = (
        db.execute(
            select(DiagnosticReplayPoint)
            .where(
                DiagnosticReplayPoint.run_id == run.id,
                DiagnosticReplayPoint.experiment_id == experiment_id,
                DiagnosticReplayPoint.vehicle_id.in_(vehicle_ids),
            )
            .order_by(
                DiagnosticReplayPoint.vehicle_id,
                DiagnosticReplayPoint.anchor_mileage,
                DiagnosticReplayPoint.id,
            )
        ).scalars().all()
        if vehicle_ids
        else []
    )

    by_vehicle: dict[str, list[DiagnosticReplayPoint]] = {}
    for point in replay_rows:
        by_vehicle.setdefault(point.vehicle_id, []).append(point)

    watchlisted_case_ids = set(
        db.execute(
            select(DiagnosticWatchlistEntry.case_id).where(
                DiagnosticWatchlistEntry.run_id == run.id,
                DiagnosticWatchlistEntry.experiment_id == experiment_id,
            )
        ).scalars().all()
    )

    plans = db.execute(
        select(DiagnosticMaintenancePlan).where(
            DiagnosticMaintenancePlan.run_id == run.id,
            DiagnosticMaintenancePlan.experiment_id == experiment_id,
        )
    ).scalars().all()
    plan_map = {row.case_id: row for row in plans}

    records = [
        _trajectory_payload(
            case,
            by_vehicle.get(case.vehicle_id, []),
            watchlisted=case.id in watchlisted_case_ids,
            plan=plan_map.get(case.id),
        )
        for case in cases
    ]

    return experiment_id, run, records


def _maintenance_plan_payload(
    row: DiagnosticMaintenancePlan,
) -> dict:
    return {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "caseId": row.case_id,
        "vehicleId": row.vehicle_id,
        "rulesVersion": row.rules_version,
        "state": row.state,
        "owner": row.owner,
        "targetMileage": (
            round(float(row.target_mileage), 1)
            if row.target_mileage is not None
            else None
        ),
        "note": row.note,
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
    }


def _maintenance_activity_payload(
    row: DiagnosticMaintenanceActivity,
) -> dict:
    return {
        "id": row.id,
        "planId": row.plan_id,
        "caseId": row.case_id,
        "vehicleId": row.vehicle_id,
        "createdAt": row.created_at.isoformat(),
        "activityType": row.activity_type,
        "actor": row.actor,
        "fromValue": row.from_value,
        "toValue": row.to_value,
        "note": row.note_text,
    }


@router.get("/prognostics/summary")
def diagnostic_prognostics_summary(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_prognostic_records(db)

    tier_counts = {
        tier: sum(
            1
            for row in records
            if row["maintenanceTier"] == tier
        )
        for tier in (
            "URGENT_REVIEW",
            "PLAN_SERVICE",
            "MONITOR",
            "ROUTINE_REVIEW",
        )
    }

    eligible = [
        row
        for row in records
        if row["trajectoryEligible"] and row["fit"] is not None
    ]
    escalating = [
        row
        for row in eligible
        if float(row["fit"]["slopePer1kMiles"]) > 0.0
    ]
    horizon_available = [
        row
        for row in eligible
        if row["experimentalHorizon"] is not None
        and row["experimentalHorizon"][
            "estimatedMilesToThreshold"
        ] is not None
    ]

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": PROGNOSTIC_RULES_VERSION,
        "targetHypothesisConfidence": TARGET_HYPOTHESIS_CONFIDENCE,
        "totalCases": len(records),
        "eligibleTrajectories": len(eligible),
        "escalatingTrajectories": len(escalating),
        "experimentalHorizonsAvailable": len(horizon_available),
        "plannedCases": sum(
            1
            for row in records
            if row["maintenancePlan"] is not None
        ),
        "byMaintenanceTier": [
            {"tier": tier, "cases": count}
            for tier, count in tier_counts.items()
        ],
        "scopePolicy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "runFrozenReplayOnly": True,
            "usesTelemetry": False,
            "usesPostRunTelemetry": False,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
            "modelRetrained": False,
            "benchmarkModified": False,
        },
        "interpretationPolicy": (
            "Prognostic horizons extrapolate persisted run-frozen model-"
            "hypothesis confidence trajectories toward a configured model "
            "confidence threshold. They are experimental investigation "
            "signals, not physical remaining useful life, failure-time "
            "estimates, calibrated failure risk, attribution, or causal proof."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/prognostics/queue")
def diagnostic_maintenance_queue(
    limit: int = Query(default=50, ge=1, le=200),
    tier: str | None = Query(default=None),
    hypothesis_class: str | None = Query(default=None),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_prognostic_records(db)

    filtered = [
        row
        for row in records
        if row["caseStatus"] != CASE_CLOSED
    ]
    if tier is not None:
        filtered = [
            row
            for row in filtered
            if row["maintenanceTier"] == tier
        ]
    if hypothesis_class is not None:
        filtered = [
            row
            for row in filtered
            if row["hypothesisClass"] == hypothesis_class
        ]

    filtered.sort(
        key=lambda row: (
            float(row["priorityScore"]),
            float(
                row["fit"]["latestConfidence"]
                if row["fit"] is not None
                else 0.0
            ),
        ),
        reverse=True,
    )

    compact = []
    for row in filtered[:limit]:
        compact.append(
            {
                key: value
                for key, value in row.items()
                if key != "trajectory"
            }
        )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": PROGNOSTIC_RULES_VERSION,
        "totalMatched": len(filtered),
        "returned": len(compact),
        "filters": {
            "tier": tier,
            "hypothesisClass": hypothesis_class,
        },
        "queue": compact,
        "interpretationPolicy": (
            "Queue score and review windows are deterministic operational "
            "triage heuristics. They are not physical-failure probabilities "
            "or mandatory service intervals."
        ),
    }


@router.get("/prognostics/cases/{case_id}")
def diagnostic_case_prognostics(
    case_id: int,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, case = _require_current_case(case_id, db)
    _, _, records = _current_prognostic_records(db)
    record = next(
        (row for row in records if row["caseId"] == case.id),
        None,
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Prognostic record unavailable for current case",
        )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": PROGNOSTIC_RULES_VERSION,
        "targetHypothesisConfidence": TARGET_HYPOTHESIS_CONFIDENCE,
        "prognostic": record,
        "interpretationPolicy": (
            "The trajectory is the selected case hypothesis confidence across "
            "persisted run-frozen replay anchors. Extrapolated miles are not "
            "physical remaining useful life or a failure-time estimate."
        ),
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


@router.get("/prognostics/backtest")
def diagnostic_prognostic_backtest(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    cases = db.execute(
        select(DiagnosticCase)
        .where(
            DiagnosticCase.run_id == run.id,
            DiagnosticCase.experiment_id == experiment_id,
        )
        .order_by(DiagnosticCase.id)
    ).scalars().all()

    vehicle_ids = sorted({row.vehicle_id for row in cases})
    points = (
        db.execute(
            select(DiagnosticReplayPoint)
            .where(
                DiagnosticReplayPoint.run_id == run.id,
                DiagnosticReplayPoint.experiment_id == experiment_id,
                DiagnosticReplayPoint.vehicle_id.in_(vehicle_ids),
            )
            .order_by(
                DiagnosticReplayPoint.vehicle_id,
                DiagnosticReplayPoint.anchor_mileage,
                DiagnosticReplayPoint.id,
            )
        ).scalars().all()
        if vehicle_ids
        else []
    )
    by_vehicle: dict[str, list[DiagnosticReplayPoint]] = {}
    for point in points:
        by_vehicle.setdefault(point.vehicle_id, []).append(point)

    evaluations = []
    for case in cases:
        trajectory = []
        for point in by_vehicle.get(case.vehicle_id, []):
            confidence = _hypothesis_confidence(
                point,
                case.hypothesis_class,
            )
            if confidence is None:
                continue
            trajectory.append(
                (float(point.anchor_mileage), float(confidence))
            )

        result = backtest_threshold_horizon(trajectory)
        if result is None:
            continue
        evaluations.append(
            {
                "hypothesisClass": case.hypothesis_class,
                **result,
            }
        )

    paired_errors = [
        float(row["absoluteErrorMiles"])
        for row in evaluations
        if row["absoluteErrorMiles"] is not None
    ]
    predicted_crossings = sum(
        1 for row in evaluations if row["predictedCrossing"]
    )
    observed_crossings = sum(
        1 for row in evaluations if row["observedFutureCrossing"]
    )

    class_rows = []
    for hypothesis_class in sorted(
        {row["hypothesisClass"] for row in evaluations}
    ):
        class_evals = [
            row
            for row in evaluations
            if row["hypothesisClass"] == hypothesis_class
        ]
        errors = [
            float(row["absoluteErrorMiles"])
            for row in class_evals
            if row["absoluteErrorMiles"] is not None
        ]
        class_rows.append(
            {
                "hypothesisClass": hypothesis_class,
                "evaluatedCases": len(class_evals),
                "pairedCrossings": len(errors),
                "medianAbsoluteErrorMiles": (
                    round(float(_median(errors)), 1)
                    if errors
                    else None
                ),
            }
        )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": PROGNOSTIC_RULES_VERSION,
        "targetHypothesisConfidence": TARGET_HYPOTHESIS_CONFIDENCE,
        "evaluatedCases": len(evaluations),
        "predictedCrossings": predicted_crossings,
        "observedFutureCrossings": observed_crossings,
        "pairedCrossings": len(paired_errors),
        "medianAbsoluteErrorMiles": (
            round(float(_median(paired_errors)), 1)
            if paired_errors
            else None
        ),
        "meanAbsoluteErrorMiles": (
            round(
                sum(paired_errors) / len(paired_errors),
                1,
            )
            if paired_errors
            else None
        ),
        "within2500Miles": (
            round(
                sum(1 for error in paired_errors if error <= 2500.0)
                / len(paired_errors),
                6,
            )
            if paired_errors
            else None
        ),
        "byClass": class_rows,
        "scopePolicy": {
            "runFrozenReplayOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
            "evaluatesModelThresholdCrossing": True,
            "evaluatesPhysicalFailure": False,
        },
        "interpretationPolicy": (
            "Backtesting compares early replay-based extrapolations with later "
            "crossings of the same model-hypothesis confidence threshold. It "
            "does not evaluate physical failures or remaining useful life."
        ),
    }


@router.get("/maintenance/plans")
def diagnostic_maintenance_plans(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    rows = db.execute(
        select(DiagnosticMaintenancePlan)
        .where(
            DiagnosticMaintenancePlan.run_id == run.id,
            DiagnosticMaintenancePlan.experiment_id == experiment_id,
        )
        .order_by(
            desc(DiagnosticMaintenancePlan.updated_at),
            desc(DiagnosticMaintenancePlan.id),
        )
    ).scalars().all()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "plans": [_maintenance_plan_payload(row) for row in rows],
        "total": len(rows),
    }


@router.get("/maintenance/plans/{case_id}")
def diagnostic_maintenance_plan_detail(
    case_id: int,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, case = _require_current_case(case_id, db)
    plan = db.execute(
        select(DiagnosticMaintenancePlan)
        .where(
            DiagnosticMaintenancePlan.run_id == run.id,
            DiagnosticMaintenancePlan.experiment_id == experiment_id,
            DiagnosticMaintenancePlan.case_id == case.id,
        )
        .limit(1)
    ).scalar_one_or_none()

    if plan is None:
        return {
            "runId": run.id,
            "experimentId": experiment_id,
            "caseId": case.id,
            "plan": None,
            "activities": [],
        }

    activities = db.execute(
        select(DiagnosticMaintenanceActivity)
        .where(
            DiagnosticMaintenanceActivity.plan_id == plan.id,
            DiagnosticMaintenanceActivity.run_id == run.id,
        )
        .order_by(
            desc(DiagnosticMaintenanceActivity.created_at),
            desc(DiagnosticMaintenanceActivity.id),
        )
    ).scalars().all()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "caseId": case.id,
        "plan": _maintenance_plan_payload(plan),
        "activities": [
            _maintenance_activity_payload(row)
            for row in activities
        ],
    }


@router.put("/maintenance/plans/{case_id}")
def upsert_diagnostic_maintenance_plan(
    case_id: int,
    request: DiagnosticMaintenancePlanUpdate,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, case = _require_current_case(case_id, db)

    if request.state is not None and request.state not in MAINTENANCE_STATES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported maintenance plan state",
                "allowed": list(MAINTENANCE_STATES),
            },
        )

    now = datetime.now(timezone.utc)
    plan = db.execute(
        select(DiagnosticMaintenancePlan)
        .where(
            DiagnosticMaintenancePlan.run_id == run.id,
            DiagnosticMaintenancePlan.case_id == case.id,
        )
        .limit(1)
    ).scalar_one_or_none()

    created = plan is None
    if plan is None:
        plan = DiagnosticMaintenancePlan(
            run_id=run.id,
            experiment_id=experiment_id,
            case_id=case.id,
            vehicle_id=case.vehicle_id,
            rules_version=PROGNOSTIC_RULES_VERSION,
            created_at=now,
            updated_at=now,
            state=request.state or "REVIEW",
            owner=(
                request.owner.strip()
                if request.owner
                else None
            ),
            target_mileage=request.target_mileage,
            note=(
                request.note.strip()
                if request.note
                else None
            ),
        )
        db.add(plan)
        db.flush()
        db.add(
            DiagnosticMaintenanceActivity(
                plan_id=plan.id,
                run_id=run.id,
                experiment_id=experiment_id,
                case_id=case.id,
                vehicle_id=case.vehicle_id,
                created_at=now,
                activity_type=MAINTENANCE_ACTIVITY_CREATED,
                actor=request.actor,
                from_value=None,
                to_value=plan.state,
                note_text=plan.note,
            )
        )
    else:
        previous_state = plan.state
        previous_owner = plan.owner
        previous_target = plan.target_mileage

        if request.state is not None:
            plan.state = request.state
        if request.clear_owner:
            plan.owner = None
        elif request.owner is not None:
            plan.owner = request.owner.strip() or None
        if request.clear_target_mileage:
            plan.target_mileage = None
        elif request.target_mileage is not None:
            plan.target_mileage = request.target_mileage
        if request.note is not None:
            stripped_note = request.note.strip()
            plan.note = stripped_note or None

        plan.updated_at = now
        db.add(plan)

        if previous_state != plan.state:
            db.add(
                DiagnosticMaintenanceActivity(
                    plan_id=plan.id,
                    run_id=run.id,
                    experiment_id=experiment_id,
                    case_id=case.id,
                    vehicle_id=case.vehicle_id,
                    created_at=now,
                    activity_type=MAINTENANCE_ACTIVITY_STATE_CHANGED,
                    actor=request.actor,
                    from_value=previous_state,
                    to_value=plan.state,
                    note_text=None,
                )
            )
        if previous_owner != plan.owner:
            db.add(
                DiagnosticMaintenanceActivity(
                    plan_id=plan.id,
                    run_id=run.id,
                    experiment_id=experiment_id,
                    case_id=case.id,
                    vehicle_id=case.vehicle_id,
                    created_at=now,
                    activity_type=MAINTENANCE_ACTIVITY_OWNER_CHANGED,
                    actor=request.actor,
                    from_value=previous_owner,
                    to_value=plan.owner,
                    note_text=None,
                )
            )
        if previous_target != plan.target_mileage:
            db.add(
                DiagnosticMaintenanceActivity(
                    plan_id=plan.id,
                    run_id=run.id,
                    experiment_id=experiment_id,
                    case_id=case.id,
                    vehicle_id=case.vehicle_id,
                    created_at=now,
                    activity_type=MAINTENANCE_ACTIVITY_TARGET_CHANGED,
                    actor=request.actor,
                    from_value=(
                        str(previous_target)
                        if previous_target is not None
                        else None
                    ),
                    to_value=(
                        str(plan.target_mileage)
                        if plan.target_mileage is not None
                        else None
                    ),
                    note_text=None,
                )
            )
        if request.note is not None and request.note.strip():
            db.add(
                DiagnosticMaintenanceActivity(
                    plan_id=plan.id,
                    run_id=run.id,
                    experiment_id=experiment_id,
                    case_id=case.id,
                    vehicle_id=case.vehicle_id,
                    created_at=now,
                    activity_type=MAINTENANCE_ACTIVITY_NOTE_ADDED,
                    actor=request.actor,
                    from_value=None,
                    to_value=None,
                    note_text=request.note.strip(),
                )
            )

    db.commit()
    db.refresh(plan)

    activities = db.execute(
        select(DiagnosticMaintenanceActivity)
        .where(
            DiagnosticMaintenanceActivity.plan_id == plan.id,
            DiagnosticMaintenanceActivity.run_id == run.id,
        )
        .order_by(
            desc(DiagnosticMaintenanceActivity.created_at),
            desc(DiagnosticMaintenanceActivity.id),
        )
    ).scalars().all()

    return {
        "created": created,
        "plan": _maintenance_plan_payload(plan),
        "activities": [
            _maintenance_activity_payload(row)
            for row in activities
        ],
        "interpretationPolicy": (
            "Maintenance plans are operator workflow metadata. Creating or "
            "updating a plan does not rewrite diagnostic replay, events, "
            "episodes, cases, model artifacts, or benchmark evidence."
        ),
    }




class DiagnosticAutomationActorRequest(BaseModel):
    actor: str = Field(default="operator", min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class DiagnosticAutomationPolicyUpdate(BaseModel):
    enabled: bool
    actor: str = Field(default="operator", min_length=1, max_length=64)


def _automation_policy_payload(row: DiagnosticAutomationPolicy) -> dict:
    return {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "rulesVersion": row.rules_version,
        "policyKey": row.policy_key,
        "name": row.name,
        "description": row.description,
        "enabled": bool(row.enabled),
        "priority": int(row.priority),
        "severity": row.severity,
        "conditions": _json_list(row.conditions_json),
        "actionType": row.action_type,
        "actionPayload": _json_object(row.action_payload_json),
        "requiresApproval": bool(row.requires_approval),
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
    }


def _automation_action_payload(row: DiagnosticAutomationAction) -> dict:
    return {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "policyId": row.policy_id,
        "policyKey": row.policy_key,
        "caseId": row.case_id,
        "vehicleId": row.vehicle_id,
        "rulesVersion": row.rules_version,
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
        "status": row.status,
        "severity": row.severity,
        "actionType": row.action_type,
        "reason": row.reason,
        "payload": _json_object(row.payload_json),
        "sourceSnapshot": _json_object(row.source_snapshot_json),
        "approvedAt": (
            row.approved_at.isoformat()
            if row.approved_at is not None
            else None
        ),
        "approvedBy": row.approved_by,
        "rejectedAt": (
            row.rejected_at.isoformat()
            if row.rejected_at is not None
            else None
        ),
        "rejectedBy": row.rejected_by,
        "executedAt": (
            row.executed_at.isoformat()
            if row.executed_at is not None
            else None
        ),
        "executedBy": row.executed_by,
        "executionResult": _json_object(row.execution_result_json),
    }


def _automation_activity_payload(row: DiagnosticAutomationActivity) -> dict:
    return {
        "id": row.id,
        "actionId": row.action_id,
        "policyId": row.policy_id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "caseId": row.case_id,
        "vehicleId": row.vehicle_id,
        "createdAt": row.created_at.isoformat(),
        "activityType": row.activity_type,
        "actor": row.actor,
        "note": row.note_text,
        "details": _json_object(row.details_json),
    }


def _automation_policy_spec(row: DiagnosticAutomationPolicy) -> dict:
    return {
        "id": row.id,
        "key": row.policy_key,
        "name": row.name,
        "description": row.description,
        "enabled": bool(row.enabled),
        "priority": int(row.priority),
        "severity": row.severity,
        "conditions": _json_list(row.conditions_json),
        "actionType": row.action_type,
        "actionPayload": _json_object(row.action_payload_json),
        "requiresApproval": bool(row.requires_approval),
    }


def _automation_source_snapshot(record: dict) -> dict:
    fit = record.get("fit") or {}
    horizon = record.get("experimentalHorizon") or {}
    return {
        "caseId": record.get("caseId"),
        "episodeId": record.get("episodeId"),
        "vehicleId": record.get("vehicleId"),
        "hypothesisClass": record.get("hypothesisClass"),
        "caseStatus": record.get("caseStatus"),
        "reviewPriority": record.get("reviewPriority"),
        "episodeState": record.get("episodeState"),
        "watchlisted": bool(record.get("watchlisted")),
        "trajectoryEligible": bool(record.get("trajectoryEligible")),
        "trajectoryPointCount": int(record.get("trajectoryPointCount") or 0),
        "latestConfidence": fit.get("latestConfidence"),
        "slopePer1kMiles": fit.get("slopePer1kMiles"),
        "priorityScore": record.get("priorityScore"),
        "maintenanceTier": record.get("maintenanceTier"),
        "recommendedReviewWindow": record.get("recommendedReviewWindow"),
        "maintenancePlanPresent": record.get("maintenancePlan") is not None,
        "thresholdAlreadyReached": bool(
            horizon.get("thresholdAlreadyReached", False)
        ),
        "estimatedMilesToThreshold": horizon.get(
            "estimatedMilesToThreshold"
        ),
    }


def _current_automation_policies(
    db: Session,
    *,
    run_id: int,
    experiment_id: str,
) -> list[DiagnosticAutomationPolicy]:
    return db.execute(
        select(DiagnosticAutomationPolicy)
        .where(
            DiagnosticAutomationPolicy.run_id == run_id,
            DiagnosticAutomationPolicy.experiment_id == experiment_id,
        )
        .order_by(
            desc(DiagnosticAutomationPolicy.priority),
            DiagnosticAutomationPolicy.policy_key,
        )
    ).scalars().all()


def _require_automation_policy(
    policy_key: str,
    db: Session,
) -> tuple[str, DiagnosticModelRun, DiagnosticAutomationPolicy]:
    experiment_id, run = _require_current_run(db)
    row = db.execute(
        select(DiagnosticAutomationPolicy)
        .where(
            DiagnosticAutomationPolicy.run_id == run.id,
            DiagnosticAutomationPolicy.experiment_id == experiment_id,
            DiagnosticAutomationPolicy.policy_key == policy_key,
        )
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Automation policy not found in the current run",
        )
    return experiment_id, run, row


def _require_automation_action(
    action_id: int,
    db: Session,
) -> tuple[str, DiagnosticModelRun, DiagnosticAutomationAction]:
    experiment_id, run = _require_current_run(db)
    row = db.execute(
        select(DiagnosticAutomationAction)
        .where(
            DiagnosticAutomationAction.id == action_id,
            DiagnosticAutomationAction.run_id == run.id,
            DiagnosticAutomationAction.experiment_id == experiment_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Automation action not found in the current run",
        )
    return experiment_id, run, row


def _automation_matches(
    records: list[dict],
    policies: list[DiagnosticAutomationPolicy],
    *,
    include_disabled: bool = False,
) -> list[dict]:
    matches = []
    for policy_row in policies:
        policy = _automation_policy_spec(policy_row)
        if not include_disabled and not policy["enabled"]:
            continue
        for record in records:
            if record.get("caseStatus") == CASE_CLOSED:
                continue
            if not policy_matches(record, policy):
                continue
            matches.append(
                {
                    "policy": policy,
                    "record": record,
                    "reason": policy_match_reason(record, policy),
                }
            )
    matches.sort(
        key=lambda item: (
            int(item["policy"]["priority"]),
            float(item["record"].get("priorityScore") or 0.0),
            -int(item["record"]["caseId"]),
        ),
        reverse=True,
    )
    return matches


def _automation_scope_policy() -> dict:
    return {
        "currentRunOnly": True,
        "exactExperimentOnly": True,
        "runFrozenPrognosticInputs": True,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "automaticExecution": False,
        "humanApprovalRequiredForDefaultPolicies": True,
        "workflowMetadataOnly": True,
        "modelRetrained": False,
        "benchmarkModified": False,
    }


@router.post("/automation/policies/bootstrap")
def bootstrap_diagnostic_automation_policies(
    request: DiagnosticAutomationActorRequest,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    existing_rows = _current_automation_policies(
        db,
        run_id=run.id,
        experiment_id=experiment_id,
    )
    existing = {row.policy_key: row for row in existing_rows}
    now = datetime.now(timezone.utc)
    created = 0

    for spec in DEFAULT_AUTOMATION_POLICIES:
        if spec["key"] in existing:
            continue
        row = DiagnosticAutomationPolicy(
            run_id=run.id,
            experiment_id=experiment_id,
            rules_version=AUTOMATION_RULES_VERSION,
            policy_key=spec["key"],
            name=spec["name"],
            description=spec["description"],
            enabled=True,
            priority=int(spec["priority"]),
            severity=spec["severity"],
            conditions_json=json.dumps(spec["conditions"], sort_keys=True),
            action_type=spec["actionType"],
            action_payload_json=json.dumps(
                spec.get("actionPayload") or {},
                sort_keys=True,
            ),
            requires_approval=bool(spec["requiresApproval"]),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        db.add(
            DiagnosticAutomationActivity(
                action_id=None,
                policy_id=row.id,
                run_id=run.id,
                experiment_id=experiment_id,
                case_id=None,
                vehicle_id=None,
                created_at=now,
                activity_type=AUTOMATION_ACTIVITY_POLICY_CREATED,
                actor=request.actor,
                note_text=(
                    "Pinned Phase 6.13 deterministic automation policy."
                ),
                details_json=json.dumps(
                    {
                        "policyKey": row.policy_key,
                        "rulesVersion": AUTOMATION_RULES_VERSION,
                    },
                    sort_keys=True,
                ),
            )
        )
        created += 1

    db.commit()
    rows = _current_automation_policies(
        db,
        run_id=run.id,
        experiment_id=experiment_id,
    )
    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": AUTOMATION_RULES_VERSION,
        "created": created,
        "totalPolicies": len(rows),
        "policies": [_automation_policy_payload(row) for row in rows],
        "scopePolicy": _automation_scope_policy(),
        "interpretationPolicy": (
            "Bootstrapping persists source-declared deterministic policies for "
            "the current diagnostic run. It does not evaluate, approve, or "
            "execute any operational action."
        ),
    }


@router.get("/automation/policies")
def diagnostic_automation_policies(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    rows = _current_automation_policies(
        db,
        run_id=run.id,
        experiment_id=experiment_id,
    )
    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": AUTOMATION_RULES_VERSION,
        "totalPolicies": len(rows),
        "enabledPolicies": sum(1 for row in rows if row.enabled),
        "policies": [_automation_policy_payload(row) for row in rows],
        "scopePolicy": _automation_scope_policy(),
    }


@router.put("/automation/policies/{policy_key}")
def update_diagnostic_automation_policy(
    policy_key: str,
    request: DiagnosticAutomationPolicyUpdate,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, row = _require_automation_policy(policy_key, db)
    previous = bool(row.enabled)
    row.enabled = bool(request.enabled)
    row.updated_at = datetime.now(timezone.utc)

    if previous != row.enabled:
        db.add(
            DiagnosticAutomationActivity(
                action_id=None,
                policy_id=row.id,
                run_id=run.id,
                experiment_id=experiment_id,
                case_id=None,
                vehicle_id=None,
                created_at=row.updated_at,
                activity_type=(
                    AUTOMATION_ACTIVITY_POLICY_ENABLED
                    if row.enabled
                    else AUTOMATION_ACTIVITY_POLICY_DISABLED
                ),
                actor=request.actor,
                note_text=None,
                details_json=json.dumps(
                    {
                        "fromEnabled": previous,
                        "toEnabled": bool(row.enabled),
                    },
                    sort_keys=True,
                ),
            )
        )

    db.commit()
    db.refresh(row)
    return {
        "policy": _automation_policy_payload(row),
        "interpretationPolicy": (
            "Only policy enablement is operator-configurable in Phase 6.13. "
            "Conditions and action semantics remain source-declared and "
            "version-pinned to prevent post-result threshold tuning."
        ),
    }


@router.get("/automation/simulate")
def simulate_diagnostic_automation(
    include_disabled: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_prognostic_records(db)
    policies = _current_automation_policies(
        db,
        run_id=run.id,
        experiment_id=experiment_id,
    )
    matches = _automation_matches(
        records,
        policies,
        include_disabled=include_disabled,
    )

    by_policy = []
    for policy in policies:
        count = sum(
            1
            for item in matches
            if item["policy"]["key"] == policy.policy_key
        )
        by_policy.append(
            {
                "policyKey": policy.policy_key,
                "enabled": bool(policy.enabled),
                "matches": count,
                "actionType": policy.action_type,
                "severity": policy.severity,
            }
        )

    action_types = sorted({item["policy"]["actionType"] for item in matches})
    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": AUTOMATION_RULES_VERSION,
        "simulationOnly": True,
        "wouldQueue": len(matches),
        "byPolicy": by_policy,
        "byActionType": [
            {
                "actionType": action_type,
                "matches": sum(
                    1
                    for item in matches
                    if item["policy"]["actionType"] == action_type
                ),
            }
            for action_type in action_types
        ],
        "sampleMatches": [
            {
                "policyKey": item["policy"]["key"],
                "policyName": item["policy"]["name"],
                "severity": item["policy"]["severity"],
                "actionType": item["policy"]["actionType"],
                "requiresApproval": item["policy"]["requiresApproval"],
                "caseId": item["record"]["caseId"],
                "vehicleId": item["record"]["vehicleId"],
                "hypothesisClass": item["record"]["hypothesisClass"],
                "maintenanceTier": item["record"]["maintenanceTier"],
                "priorityScore": item["record"]["priorityScore"],
                "reason": item["reason"],
            }
            for item in matches[:limit]
        ],
        "scopePolicy": _automation_scope_policy(),
        "interpretationPolicy": (
            "Dry-run simulation evaluates deterministic policies against "
            "current run-frozen prognostic workflow inputs. It writes no "
            "actions and performs no operational execution."
        ),
    }


@router.post("/automation/evaluate")
def evaluate_diagnostic_automation(
    request: DiagnosticAutomationActorRequest,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_prognostic_records(db)
    policies = _current_automation_policies(
        db,
        run_id=run.id,
        experiment_id=experiment_id,
    )
    if not policies:
        raise HTTPException(
            status_code=409,
            detail=(
                "No persisted automation policies exist for the current run; "
                "bootstrap policies first"
            ),
        )

    matches = _automation_matches(records, policies)
    existing_rows = db.execute(
        select(DiagnosticAutomationAction).where(
            DiagnosticAutomationAction.run_id == run.id,
            DiagnosticAutomationAction.experiment_id == experiment_id,
        )
    ).scalars().all()
    existing_keys = {
        (row.case_id, row.policy_key)
        for row in existing_rows
    }
    now = datetime.now(timezone.utc)
    created = 0
    skipped_existing = 0

    policy_by_key = {row.policy_key: row for row in policies}
    for item in matches:
        policy = item["policy"]
        record = item["record"]
        key = (int(record["caseId"]), str(policy["key"]))
        if key in existing_keys:
            skipped_existing += 1
            continue

        policy_row = policy_by_key[policy["key"]]
        action = DiagnosticAutomationAction(
            run_id=run.id,
            experiment_id=experiment_id,
            policy_id=policy_row.id,
            policy_key=policy_row.policy_key,
            case_id=int(record["caseId"]),
            vehicle_id=str(record["vehicleId"]),
            rules_version=AUTOMATION_RULES_VERSION,
            created_at=now,
            updated_at=now,
            status=AUTOMATION_STATUS_PENDING_APPROVAL,
            severity=policy_row.severity,
            action_type=policy_row.action_type,
            reason=item["reason"],
            payload_json=json.dumps(
                policy.get("actionPayload") or {},
                sort_keys=True,
            ),
            source_snapshot_json=json.dumps(
                _automation_source_snapshot(record),
                sort_keys=True,
            ),
            approved_at=None,
            approved_by=None,
            rejected_at=None,
            rejected_by=None,
            executed_at=None,
            executed_by=None,
            execution_result_json="{}",
        )
        db.add(action)
        db.flush()
        db.add(
            DiagnosticAutomationActivity(
                action_id=action.id,
                policy_id=policy_row.id,
                run_id=run.id,
                experiment_id=experiment_id,
                case_id=action.case_id,
                vehicle_id=action.vehicle_id,
                created_at=now,
                activity_type=AUTOMATION_ACTIVITY_ACTION_CREATED,
                actor=request.actor,
                note_text=request.note,
                details_json=json.dumps(
                    {
                        "status": AUTOMATION_STATUS_PENDING_APPROVAL,
                        "actionType": action.action_type,
                        "policyKey": action.policy_key,
                    },
                    sort_keys=True,
                ),
            )
        )
        existing_keys.add(key)
        created += 1

    db.commit()
    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": AUTOMATION_RULES_VERSION,
        "matched": len(matches),
        "created": created,
        "skippedExisting": skipped_existing,
        "executionPerformed": False,
        "scopePolicy": _automation_scope_policy(),
        "interpretationPolicy": (
            "Evaluation materializes approval-pending workflow actions only. "
            "No action is automatically approved or executed."
        ),
    }


@router.get("/automation/summary")
def diagnostic_automation_summary(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    policies = _current_automation_policies(
        db,
        run_id=run.id,
        experiment_id=experiment_id,
    )
    actions = db.execute(
        select(DiagnosticAutomationAction).where(
            DiagnosticAutomationAction.run_id == run.id,
            DiagnosticAutomationAction.experiment_id == experiment_id,
        )
    ).scalars().all()
    status_counts = {
        status: sum(1 for row in actions if row.status == status)
        for status in AUTOMATION_ACTION_STATUSES
    }
    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": AUTOMATION_RULES_VERSION,
        "totalPolicies": len(policies),
        "enabledPolicies": sum(1 for row in policies if row.enabled),
        "totalActions": len(actions),
        "pendingApproval": status_counts[
            AUTOMATION_STATUS_PENDING_APPROVAL
        ],
        "approvedReady": status_counts[AUTOMATION_STATUS_APPROVED],
        "rejected": status_counts[AUTOMATION_STATUS_REJECTED],
        "executed": status_counts[AUTOMATION_STATUS_EXECUTED],
        "byStatus": [
            {"status": status, "actions": status_counts[status]}
            for status in AUTOMATION_ACTION_STATUSES
        ],
        "scopePolicy": _automation_scope_policy(),
        "interpretationPolicy": (
            "Automation counts are approval-workflow metadata. Pending or "
            "executed actions are not physical-failure labels, probabilities, "
            "or evidence that a component actually failed."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/automation/actions")
def diagnostic_automation_actions(
    limit: int = Query(default=100, ge=1, le=500),
    status: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    case_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    if status is not None and status not in AUTOMATION_ACTION_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported automation action status",
                "allowed": list(AUTOMATION_ACTION_STATUSES),
            },
        )
    if action_type is not None and action_type not in AUTOMATION_ACTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported automation action type",
                "allowed": list(AUTOMATION_ACTION_TYPES),
            },
        )

    filters = [
        DiagnosticAutomationAction.run_id == run.id,
        DiagnosticAutomationAction.experiment_id == experiment_id,
    ]
    if status is not None:
        filters.append(DiagnosticAutomationAction.status == status)
    if action_type is not None:
        filters.append(DiagnosticAutomationAction.action_type == action_type)
    if case_id is not None:
        filters.append(DiagnosticAutomationAction.case_id == case_id)

    total = int(
        db.scalar(
            select(func.count(DiagnosticAutomationAction.id)).where(*filters)
        )
        or 0
    )
    rows = db.execute(
        select(DiagnosticAutomationAction)
        .where(*filters)
        .order_by(
            desc(DiagnosticAutomationAction.created_at),
            desc(DiagnosticAutomationAction.id),
        )
        .limit(limit)
    ).scalars().all()
    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": AUTOMATION_RULES_VERSION,
        "totalMatched": total,
        "returned": len(rows),
        "filters": {
            "status": status,
            "actionType": action_type,
            "caseId": case_id,
        },
        "actions": [_automation_action_payload(row) for row in rows],
        "scopePolicy": _automation_scope_policy(),
    }


@router.get("/automation/actions/{action_id}")
def diagnostic_automation_action_detail(
    action_id: int,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, row = _require_automation_action(action_id, db)
    policy = db.execute(
        select(DiagnosticAutomationPolicy)
        .where(
            DiagnosticAutomationPolicy.id == row.policy_id,
            DiagnosticAutomationPolicy.run_id == run.id,
            DiagnosticAutomationPolicy.experiment_id == experiment_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    activities = db.execute(
        select(DiagnosticAutomationActivity)
        .where(
            DiagnosticAutomationActivity.run_id == run.id,
            DiagnosticAutomationActivity.experiment_id == experiment_id,
            DiagnosticAutomationActivity.action_id == row.id,
        )
        .order_by(
            desc(DiagnosticAutomationActivity.created_at),
            desc(DiagnosticAutomationActivity.id),
        )
    ).scalars().all()
    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "action": _automation_action_payload(row),
        "policy": (
            _automation_policy_payload(policy)
            if policy is not None
            else None
        ),
        "activities": [
            _automation_activity_payload(activity)
            for activity in activities
        ],
        "scopePolicy": _automation_scope_policy(),
    }


@router.post("/automation/actions/{action_id}/approve")
def approve_diagnostic_automation_action(
    action_id: int,
    request: DiagnosticAutomationActorRequest,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, row = _require_automation_action(action_id, db)
    if row.status == AUTOMATION_STATUS_APPROVED:
        return {
            "changed": False,
            "action": _automation_action_payload(row),
        }
    if row.status != AUTOMATION_STATUS_PENDING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=(
                "Only PENDING_APPROVAL automation actions can be approved"
            ),
        )

    now = datetime.now(timezone.utc)
    row.status = AUTOMATION_STATUS_APPROVED
    row.approved_at = now
    row.approved_by = request.actor
    row.updated_at = now
    db.add(
        DiagnosticAutomationActivity(
            action_id=row.id,
            policy_id=row.policy_id,
            run_id=run.id,
            experiment_id=experiment_id,
            case_id=row.case_id,
            vehicle_id=row.vehicle_id,
            created_at=now,
            activity_type=AUTOMATION_ACTIVITY_ACTION_APPROVED,
            actor=request.actor,
            note_text=request.note,
            details_json=json.dumps(
                {"fromStatus": AUTOMATION_STATUS_PENDING_APPROVAL,
                 "toStatus": AUTOMATION_STATUS_APPROVED},
                sort_keys=True,
            ),
        )
    )
    db.commit()
    db.refresh(row)
    return {
        "changed": True,
        "action": _automation_action_payload(row),
        "interpretationPolicy": (
            "Approval authorizes a later explicit execution request; approval "
            "alone performs no workflow mutation."
        ),
    }


@router.post("/automation/actions/{action_id}/reject")
def reject_diagnostic_automation_action(
    action_id: int,
    request: DiagnosticAutomationActorRequest,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, row = _require_automation_action(action_id, db)
    if row.status == AUTOMATION_STATUS_REJECTED:
        return {
            "changed": False,
            "action": _automation_action_payload(row),
        }
    if row.status not in (
        AUTOMATION_STATUS_PENDING_APPROVAL,
        AUTOMATION_STATUS_APPROVED,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Only pending or approved automation actions can be rejected"
            ),
        )

    previous = row.status
    now = datetime.now(timezone.utc)
    row.status = AUTOMATION_STATUS_REJECTED
    row.rejected_at = now
    row.rejected_by = request.actor
    row.updated_at = now
    db.add(
        DiagnosticAutomationActivity(
            action_id=row.id,
            policy_id=row.policy_id,
            run_id=run.id,
            experiment_id=experiment_id,
            case_id=row.case_id,
            vehicle_id=row.vehicle_id,
            created_at=now,
            activity_type=AUTOMATION_ACTIVITY_ACTION_REJECTED,
            actor=request.actor,
            note_text=request.note,
            details_json=json.dumps(
                {
                    "fromStatus": previous,
                    "toStatus": AUTOMATION_STATUS_REJECTED,
                },
                sort_keys=True,
            ),
        )
    )
    db.commit()
    db.refresh(row)
    return {
        "changed": True,
        "action": _automation_action_payload(row),
    }


def _execute_approved_automation_workflow(
    *,
    row: DiagnosticAutomationAction,
    case: DiagnosticCase,
    actor: str,
    db: Session,
    run: DiagnosticModelRun,
    experiment_id: str,
    now: datetime,
) -> dict:
    if row.action_type == AUTOMATION_ACTION_ENSURE_REVIEW_PLAN:
        plan = db.execute(
            select(DiagnosticMaintenancePlan)
            .where(
                DiagnosticMaintenancePlan.run_id == run.id,
                DiagnosticMaintenancePlan.experiment_id == experiment_id,
                DiagnosticMaintenancePlan.case_id == case.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if plan is not None:
            return {
                "outcome": "ALREADY_EXISTS",
                "workflowType": "MAINTENANCE_PLAN",
                "planId": plan.id,
                "state": plan.state,
            }

        plan = DiagnosticMaintenancePlan(
            run_id=run.id,
            experiment_id=experiment_id,
            case_id=case.id,
            vehicle_id=case.vehicle_id,
            rules_version=PROGNOSTIC_RULES_VERSION,
            created_at=now,
            updated_at=now,
            state="REVIEW",
            owner=None,
            target_mileage=None,
            note=(
                f"Created by approved automation action {row.id} from policy "
                f"{row.policy_key}. Workflow metadata only; no physical "
                "failure conclusion is implied."
            ),
        )
        db.add(plan)
        db.flush()
        db.add(
            DiagnosticMaintenanceActivity(
                plan_id=plan.id,
                run_id=run.id,
                experiment_id=experiment_id,
                case_id=case.id,
                vehicle_id=case.vehicle_id,
                created_at=now,
                activity_type=MAINTENANCE_ACTIVITY_CREATED,
                actor=actor,
                from_value=None,
                to_value="REVIEW",
                note_text=plan.note,
            )
        )
        return {
            "outcome": "CREATED",
            "workflowType": "MAINTENANCE_PLAN",
            "planId": plan.id,
            "state": plan.state,
        }

    if row.action_type == AUTOMATION_ACTION_ENSURE_WATCHLIST:
        watchlist = db.execute(
            select(DiagnosticWatchlistEntry)
            .where(
                DiagnosticWatchlistEntry.run_id == run.id,
                DiagnosticWatchlistEntry.experiment_id == experiment_id,
                DiagnosticWatchlistEntry.case_id == case.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if watchlist is not None:
            return {
                "outcome": "ALREADY_EXISTS",
                "workflowType": "WATCHLIST",
                "watchlistId": watchlist.id,
            }

        watchlist = DiagnosticWatchlistEntry(
            run_id=run.id,
            experiment_id=experiment_id,
            case_id=case.id,
            vehicle_id=case.vehicle_id,
            created_at=now,
            actor=actor,
            note=(
                f"Added by approved automation action {row.id} from policy "
                f"{row.policy_key}."
            ),
        )
        db.add(watchlist)
        db.flush()
        return {
            "outcome": "CREATED",
            "workflowType": "WATCHLIST",
            "watchlistId": watchlist.id,
        }

    raise HTTPException(
        status_code=422,
        detail=f"Unsupported automation action type: {row.action_type}",
    )


@router.post("/automation/actions/{action_id}/execute")
def execute_diagnostic_automation_action(
    action_id: int,
    request: DiagnosticAutomationActorRequest,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, row = _require_automation_action(action_id, db)
    if row.status == AUTOMATION_STATUS_EXECUTED:
        return {
            "changed": False,
            "action": _automation_action_payload(row),
            "executionResult": _json_object(row.execution_result_json),
        }
    if row.status != AUTOMATION_STATUS_APPROVED:
        raise HTTPException(
            status_code=409,
            detail=(
                "Human approval is required before an automation action can "
                "be executed"
            ),
        )

    _, _, case = _require_current_case(row.case_id, db)
    if case.vehicle_id != row.vehicle_id:
        raise HTTPException(
            status_code=409,
            detail="Automation action case/vehicle identity mismatch",
        )
    if case.status == CASE_CLOSED:
        raise HTTPException(
            status_code=409,
            detail="Closed diagnostic cases cannot receive automation execution",
        )

    now = datetime.now(timezone.utc)
    result = _execute_approved_automation_workflow(
        row=row,
        case=case,
        actor=request.actor,
        db=db,
        run=run,
        experiment_id=experiment_id,
        now=now,
    )
    row.status = AUTOMATION_STATUS_EXECUTED
    row.executed_at = now
    row.executed_by = request.actor
    row.execution_result_json = json.dumps(result, sort_keys=True)
    row.updated_at = now
    db.add(
        DiagnosticAutomationActivity(
            action_id=row.id,
            policy_id=row.policy_id,
            run_id=run.id,
            experiment_id=experiment_id,
            case_id=row.case_id,
            vehicle_id=row.vehicle_id,
            created_at=now,
            activity_type=AUTOMATION_ACTIVITY_ACTION_EXECUTED,
            actor=request.actor,
            note_text=request.note,
            details_json=json.dumps(result, sort_keys=True),
        )
    )
    db.commit()
    db.refresh(row)
    return {
        "changed": True,
        "action": _automation_action_payload(row),
        "executionResult": result,
        "scopePolicy": _automation_scope_policy(),
        "interpretationPolicy": (
            "Execution is approval-gated and limited to operational workflow "
            "metadata. It does not rewrite replay, events, episodes, case "
            "evidence, model artifacts, benchmark evidence, or private failure "
            "truth."
        ),
    }

# Phase 7.0 — Fleet State & Decision Intelligence
#
# This layer synthesizes current-run model outputs, run-frozen prognostic
# records, and explicit workflow metadata. The resulting decision state,
# attention score, workload units, coverage gaps, cohorts and scenarios are
# operational constructs only. They are not physical health states, failure
# probabilities, RUL, attribution, causal proof, or labor-hour estimates.


class FleetDecisionScenarioRequest(BaseModel):
    scenario: str


class FleetDecisionSnapshotCreate(BaseModel):
    actor: str = Field(default="operator", min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=160)


def _fleet_decision_scope_policy() -> dict:
    return {
        "currentRunOnly": True,
        "exactExperimentOnly": True,
        "runFrozenPrognosticInputs": True,
        "usesTelemetry": False,
        "usesPostRunTelemetry": False,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "automaticExecution": False,
        "workflowScenarioWrites": False,
        "physicalRiskScore": False,
        "modelRetrained": False,
        "benchmarkModified": False,
    }


def _current_fleet_decision_records(
    db: Session,
    *,
    selected_run: DiagnosticModelRun | None = None,
) -> tuple[str, DiagnosticModelRun, list[dict]]:
    if selected_run is None:
        experiment_id, run = _require_current_run(db)
    else:
        run = selected_run
        experiment_id = run.experiment_id

    predictions = db.execute(
        select(DiagnosticPrediction)
        .where(
            DiagnosticPrediction.run_id == run.id,
            DiagnosticPrediction.experiment_id == experiment_id,
        )
        .order_by(DiagnosticPrediction.vehicle_id)
    ).scalars().all()

    _, prognostic_run, prognostic_records = _current_prognostic_records(
        db,
        selected_run=run,
    )
    if prognostic_run.id != run.id:
        raise HTTPException(
            status_code=409,
            detail="Prognostic records are not aligned to the current run",
        )

    cases = db.execute(
        select(DiagnosticCase).where(
            DiagnosticCase.run_id == run.id,
            DiagnosticCase.experiment_id == experiment_id,
        )
    ).scalars().all()
    case_map = {row.id: row for row in cases}

    best_prognostic_by_vehicle: dict[str, dict] = {}
    for record in prognostic_records:
        vehicle_id = str(record["vehicleId"])
        previous = best_prognostic_by_vehicle.get(vehicle_id)
        if previous is None or float(record.get("priorityScore") or 0.0) > float(
            previous.get("priorityScore") or 0.0
        ):
            best_prognostic_by_vehicle[vehicle_id] = record

    actions = db.execute(
        select(DiagnosticAutomationAction).where(
            DiagnosticAutomationAction.run_id == run.id,
            DiagnosticAutomationAction.experiment_id == experiment_id,
        )
    ).scalars().all()

    automation_by_vehicle: dict[str, list[DiagnosticAutomationAction]] = {}
    for action in actions:
        automation_by_vehicle.setdefault(action.vehicle_id, []).append(action)

    records: list[dict] = []
    for prediction in predictions:
        prognostic = best_prognostic_by_vehicle.get(prediction.vehicle_id)
        case = (
            case_map.get(int(prognostic["caseId"]))
            if prognostic is not None
            else None
        )
        plan = (
            prognostic.get("maintenancePlan")
            if prognostic is not None
            else None
        )
        vehicle_actions = automation_by_vehicle.get(prediction.vehicle_id, [])
        automation_statuses = sorted({row.status for row in vehicle_actions})
        pending_action_types = sorted(
            {
                row.action_type
                for row in vehicle_actions
                if row.status == AUTOMATION_STATUS_PENDING_APPROVAL
            }
        )

        input_record = {
            "vehicleId": prediction.vehicle_id,
            "topClass": prediction.top_class,
            "topConfidence": round(float(prediction.top_confidence), 6),
            "anchorTimestamp": prediction.anchor_timestamp.isoformat(),
            "anchorMileage": round(float(prediction.anchor_mileage), 1),
            "caseId": (
                int(prognostic["caseId"])
                if prognostic is not None
                else None
            ),
            "episodeId": (
                int(prognostic["episodeId"])
                if prognostic is not None
                else None
            ),
            "caseStatus": (
                prognostic.get("caseStatus")
                if prognostic is not None
                else None
            ),
            "reviewPriority": (
                prognostic.get("reviewPriority")
                if prognostic is not None
                else None
            ),
            "assignedTo": case.assigned_to if case is not None else None,
            "episodeState": (
                prognostic.get("episodeState")
                if prognostic is not None
                else None
            ),
            "maintenanceTier": (
                prognostic.get("maintenanceTier")
                if prognostic is not None
                else None
            ),
            "maintenancePlanState": (
                plan.get("state")
                if isinstance(plan, dict)
                else None
            ),
            "maintenancePlanId": (
                plan.get("id")
                if isinstance(plan, dict)
                else None
            ),
            "watchlisted": bool(
                prognostic.get("watchlisted")
                if prognostic is not None
                else False
            ),
            "trajectoryEligible": (
                bool(prognostic.get("trajectoryEligible"))
                if prognostic is not None
                else None
            ),
            "priorityScore": (
                prognostic.get("priorityScore")
                if prognostic is not None
                else None
            ),
            "recommendedReviewWindow": (
                prognostic.get("recommendedReviewWindow")
                if prognostic is not None
                else None
            ),
            "automationStatuses": automation_statuses,
            "pendingActionTypes": pending_action_types,
            "automationActionIds": sorted(row.id for row in vehicle_actions),
        }
        records.append(derive_fleet_decision(input_record))

    records.sort(
        key=lambda row: (
            float(row.get("attentionScore") or 0.0),
            float(row.get("topConfidence") or 0.0),
            row["vehicleId"],
        ),
        reverse=True,
    )
    return experiment_id, run, records


def _fleet_decision_snapshot_payload(
    row: DiagnosticFleetDecisionSnapshot,
    *,
    include_records: bool = False,
) -> dict:
    payload = {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "rulesVersion": row.rules_version,
        "createdAt": row.created_at.isoformat(),
        "actor": row.actor,
        "label": row.label,
        "stateHash": row.state_hash,
        "vehicleCount": int(row.vehicle_count),
        "summary": _json_object(row.summary_json),
    }
    if include_records:
        payload["records"] = _json_list(row.records_json)
    return payload


@router.get("/fleet-intelligence/summary")
def fleet_decision_summary(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_fleet_decision_records(db)
    summary = summarize_fleet_records(records)
    snapshot_count = int(
        db.scalar(
            select(func.count(DiagnosticFleetDecisionSnapshot.id)).where(
                DiagnosticFleetDecisionSnapshot.run_id == run.id,
                DiagnosticFleetDecisionSnapshot.experiment_id == experiment_id,
            )
        )
        or 0
    )
    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": FLEET_DECISION_RULES_VERSION,
        **summary,
        "snapshots": snapshot_count,
        "scopePolicy": _fleet_decision_scope_policy(),
        "interpretationPolicy": (
            "Fleet decision state, attention score, workload units and coverage "
            "debt are deterministic operational constructs derived from current-"
            "run model hypotheses and workflow metadata. They are not physical "
            "health or failure-risk scores, RUL, attribution, or causal proof."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/fleet-intelligence/vehicles")
def fleet_decision_vehicles(
    limit: int = Query(default=100, ge=1, le=500),
    decision_state: str | None = Query(default=None),
    gap: str | None = Query(default=None),
    hypothesis_class: str | None = Query(default=None),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_fleet_decision_records(db)

    if decision_state is not None and decision_state not in DECISION_STATES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported fleet decision state",
                "allowed": list(DECISION_STATES),
            },
        )
    if gap is not None and gap not in COVERAGE_GAPS:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported fleet coverage gap",
                "allowed": list(COVERAGE_GAPS),
            },
        )

    filtered = records
    if decision_state is not None:
        filtered = [
            row
            for row in filtered
            if row["decisionState"] == decision_state
        ]
    if gap is not None:
        filtered = [
            row
            for row in filtered
            if gap in row["coverageGaps"]
        ]
    if hypothesis_class is not None:
        filtered = [
            row
            for row in filtered
            if row["topClass"] == hypothesis_class
        ]

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": FLEET_DECISION_RULES_VERSION,
        "totalMatched": len(filtered),
        "returned": min(limit, len(filtered)),
        "filters": {
            "decisionState": decision_state,
            "gap": gap,
            "hypothesisClass": hypothesis_class,
        },
        "vehicles": filtered[:limit],
        "scopePolicy": _fleet_decision_scope_policy(),
    }


@router.get("/fleet-intelligence/vehicles/{vehicle_id}")
def fleet_decision_vehicle_detail(
    vehicle_id: str,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_fleet_decision_records(db)
    record = next(
        (row for row in records if row["vehicleId"] == vehicle_id),
        None,
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Vehicle is not present in current fleet decision state",
        )
    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": FLEET_DECISION_RULES_VERSION,
        "vehicle": record,
        "scopePolicy": _fleet_decision_scope_policy(),
        "interpretationPolicy": (
            "Vehicle decision state is an operational synthesis of model "
            "hypothesis and workflow metadata, not a physical digital-twin "
            "claim or proof of component condition."
        ),
    }


@router.get("/fleet-intelligence/coverage")
def fleet_decision_coverage(
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_fleet_decision_records(db)
    rows = []
    for gap in COVERAGE_GAPS:
        affected = [
            record
            for record in records
            if gap in record["coverageGaps"]
        ]
        rows.append(
            {
                "gap": gap,
                "vehicles": len(affected),
                "workloadUnits": round(
                    sum(float(row["workloadUnits"]) for row in affected),
                    2,
                ),
                "averageAttentionScore": (
                    round(
                        sum(float(row["attentionScore"]) for row in affected)
                        / len(affected),
                        3,
                    )
                    if affected
                    else None
                ),
            }
        )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": FLEET_DECISION_RULES_VERSION,
        "vehiclesWithCoverageGaps": sum(
            1 for record in records if record["coverageGaps"]
        ),
        "coverageGapInstances": sum(row["vehicles"] for row in rows),
        "gaps": rows,
        "scopePolicy": _fleet_decision_scope_policy(),
    }


@router.get("/fleet-intelligence/cohorts")
def fleet_decision_cohorts(
    dimension: str = Query(default="hypothesisClass"),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_fleet_decision_records(db)
    if dimension not in COHORT_DIMENSIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported fleet decision cohort dimension",
                "allowed": list(COHORT_DIMENSIONS),
            },
        )

    field_map = {
        "hypothesisClass": "topClass",
        "decisionState": "decisionState",
        "maintenanceTier": "maintenanceTier",
        "reviewPriority": "reviewPriority",
    }

    grouped: dict[str, list[dict]] = {}
    if dimension == "automationStatus":
        for record in records:
            statuses = record.get("automationStatuses") or ["NONE"]
            for status in statuses:
                grouped.setdefault(str(status), []).append(record)
    else:
        field = field_map[dimension]
        for record in records:
            key = str(record.get(field) or "NONE")
            grouped.setdefault(key, []).append(record)

    cohorts = []
    for key, members in grouped.items():
        cohorts.append(
            {
                "key": key,
                "vehicles": len(members),
                "workloadUnits": round(
                    sum(float(row["workloadUnits"]) for row in members),
                    2,
                ),
                "coverageGapInstances": sum(
                    len(row["coverageGaps"]) for row in members
                ),
                "averageAttentionScore": round(
                    sum(float(row["attentionScore"]) for row in members)
                    / len(members),
                    3,
                ),
            }
        )
    cohorts.sort(
        key=lambda row: (
            float(row["workloadUnits"]),
            int(row["vehicles"]),
            row["key"],
        ),
        reverse=True,
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": FLEET_DECISION_RULES_VERSION,
        "dimension": dimension,
        "cohorts": cohorts,
        "interpretationPolicy": (
            "Cohorts describe concentration of current operational attention and "
            "workflow load. They do not estimate normalized physical failure risk "
            "or causal effects."
        ),
    }


@router.post("/fleet-intelligence/scenario")
def fleet_decision_scenario(
    request: FleetDecisionScenarioRequest,
    db: Session = Depends(db_session),
) -> dict:
    if request.scenario not in FLEET_DECISION_SCENARIOS:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported fleet workflow scenario",
                "allowed": list(FLEET_DECISION_SCENARIOS),
            },
        )

    experiment_id, run, records = _current_fleet_decision_records(db)
    simulated = [
        apply_workflow_scenario(record, request.scenario)
        for record in records
    ]
    before = summarize_fleet_records(records)
    after = summarize_fleet_records(simulated)

    transitions: dict[tuple[str, str], int] = {}
    changed_vehicles = 0
    for current, projected in zip(records, simulated):
        changed = (
            current["decisionState"] != projected["decisionState"]
            or current["coverageGaps"] != projected["coverageGaps"]
            or current["workloadUnits"] != projected["workloadUnits"]
        )
        if changed:
            changed_vehicles += 1
        if current["decisionState"] != projected["decisionState"]:
            key = (
                current["decisionState"],
                projected["decisionState"],
            )
            transitions[key] = transitions.get(key, 0) + 1

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": FLEET_DECISION_RULES_VERSION,
        "scenario": request.scenario,
        "simulationOnly": True,
        "changedVehicles": changed_vehicles,
        "before": before,
        "after": after,
        "deltas": {
            "workloadUnits": round(
                float(after["totalWorkloadUnits"])
                - float(before["totalWorkloadUnits"]),
                2,
            ),
            "vehiclesWithCoverageGaps": (
                int(after["vehiclesWithCoverageGaps"])
                - int(before["vehiclesWithCoverageGaps"])
            ),
            "coverageGapInstances": (
                int(after["coverageGapInstances"])
                - int(before["coverageGapInstances"])
            ),
        },
        "stateTransitions": [
            {
                "fromState": from_state,
                "toState": to_state,
                "vehicles": count,
            }
            for (from_state, to_state), count in sorted(
                transitions.items()
            )
        ],
        "scopePolicy": _fleet_decision_scope_policy(),
        "interpretationPolicy": (
            "Scenario results are no-write workflow counterfactuals. They change "
            "assumptions about assignment, approval-queue execution, plans and "
            "watchlists only; they do not project physical failures, component "
            "health, maintenance outcomes, labor hours, or causal effects."
        ),
    }


@router.post("/fleet-intelligence/snapshots")
def create_fleet_decision_snapshot(
    request: FleetDecisionSnapshotCreate,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_fleet_decision_records(db)
    summary = summarize_fleet_records(records)
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    state_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    existing = db.execute(
        select(DiagnosticFleetDecisionSnapshot)
        .where(
            DiagnosticFleetDecisionSnapshot.run_id == run.id,
            DiagnosticFleetDecisionSnapshot.experiment_id == experiment_id,
            DiagnosticFleetDecisionSnapshot.rules_version
            == FLEET_DECISION_RULES_VERSION,
            DiagnosticFleetDecisionSnapshot.state_hash == state_hash,
        )
        .limit(1)
    ).scalar_one_or_none()

    if existing is not None:
        return {
            "created": False,
            "snapshot": _fleet_decision_snapshot_payload(existing),
            "interpretationPolicy": (
                "Identical derived fleet state already has a checkpoint. No "
                "diagnostic evidence or workflow metadata was modified."
            ),
        }

    row = DiagnosticFleetDecisionSnapshot(
        run_id=run.id,
        experiment_id=experiment_id,
        rules_version=FLEET_DECISION_RULES_VERSION,
        created_at=datetime.now(timezone.utc),
        actor=request.actor,
        label=(
            request.label.strip()
            if request.label is not None and request.label.strip()
            else None
        ),
        state_hash=state_hash,
        vehicle_count=len(records),
        summary_json=json.dumps(summary, sort_keys=True),
        records_json=canonical,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "created": True,
        "snapshot": _fleet_decision_snapshot_payload(row),
        "scopePolicy": _fleet_decision_scope_policy(),
        "interpretationPolicy": (
            "Snapshot persistence stores derived fleet decision state only. It "
            "does not rewrite predictions, replay, events, episodes, cases, "
            "maintenance plans, automation actions, model artifacts, benchmark "
            "evidence, or private failure truth."
        ),
    }


@router.get("/fleet-intelligence/snapshots")
def fleet_decision_snapshots(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    total = int(
        db.scalar(
            select(func.count(DiagnosticFleetDecisionSnapshot.id)).where(
                DiagnosticFleetDecisionSnapshot.run_id == run.id,
                DiagnosticFleetDecisionSnapshot.experiment_id == experiment_id,
            )
        )
        or 0
    )
    rows = db.execute(
        select(DiagnosticFleetDecisionSnapshot)
        .where(
            DiagnosticFleetDecisionSnapshot.run_id == run.id,
            DiagnosticFleetDecisionSnapshot.experiment_id == experiment_id,
        )
        .order_by(
            desc(DiagnosticFleetDecisionSnapshot.created_at),
            desc(DiagnosticFleetDecisionSnapshot.id),
        )
        .limit(limit)
    ).scalars().all()
    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": FLEET_DECISION_RULES_VERSION,
        "total": total,
        "returned": len(rows),
        "snapshots": [
            _fleet_decision_snapshot_payload(row)
            for row in rows
        ],
        "scopePolicy": _fleet_decision_scope_policy(),
    }


@router.get("/fleet-intelligence/snapshots/{snapshot_id}")
def fleet_decision_snapshot_detail(
    snapshot_id: int,
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _require_current_run(db)
    row = db.execute(
        select(DiagnosticFleetDecisionSnapshot)
        .where(
            DiagnosticFleetDecisionSnapshot.id == snapshot_id,
            DiagnosticFleetDecisionSnapshot.run_id == run.id,
            DiagnosticFleetDecisionSnapshot.experiment_id == experiment_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Fleet decision snapshot not found in current run",
        )
    return {
        "snapshot": _fleet_decision_snapshot_payload(
            row,
            include_records=True,
        ),
        "scopePolicy": _fleet_decision_scope_policy(),
    }

# Phase 7.1 — Vehicle Operational Digital Twin
# Operational/diagnostic state only: not a physics twin, failure-truth view,
# causal graph, component-condition proof, or physical RUL model.

class VehicleTwinSnapshotCreate(BaseModel):
    actor: str = Field(default="operator", min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=160)


def _vehicle_twin_scope_policy() -> dict:
    return {
        "currentRunOnly": False,
        "selectedRunOnly": True,
        "defaultRunSelection": "latest_persisted_trained_run",
        "activeTelemetryExperimentRequired": False,
        "exactExperimentOnly": True,
        "runFrozenReplayOnly": True,
        "observableTelemetryContextOnly": True,
        "telemetryContextBoundedToPredictionAnchor": True,
        "postRunTelemetryUsed": False,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "physicsTwin": False,
        "physicalConditionProof": False,
        "physicalRul": False,
        "causalGraph": False,
        "modelRetrained": False,
        "benchmarkModified": False,
    }


def _vehicle_twin_snapshot_payload(row, include_twin: bool = False) -> dict:
    out = {
        "id": row.id, "runId": row.run_id, "experimentId": row.experiment_id,
        "vehicleId": row.vehicle_id, "rulesVersion": row.rules_version,
        "createdAt": row.created_at.isoformat(), "actor": row.actor,
        "label": row.label, "stateHash": row.state_hash,
    }
    if include_twin:
        out["twin"] = _json_object(row.twin_json)
    return out


def _resolve_vehicle_twin_run(
    db: Session,
    run_id: int | None = None,
) -> tuple[str, DiagnosticModelRun]:
    """
    Resolve the diagnostic run used by the Phase 7.1 operational twin.

    Explicit run selection is authoritative. Without run_id, select the latest
    persisted trained diagnostic run rather than deriving identity from the
    newest telemetry experiment. This prevents an unrelated simulator restart
    from changing or orphaning the operational twin.
    """

    if run_id is not None:
        run = db.get(DiagnosticModelRun, run_id)

        if run is None:
            raise HTTPException(
                status_code=404,
                detail=f"Diagnostic run {run_id} does not exist",
            )

        if run.status != "trained":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Diagnostic run {run_id} is not a trained operational run"
                ),
            )
    else:
        run = db.execute(
            select(DiagnosticModelRun)
            .where(DiagnosticModelRun.status == "trained")
            .order_by(
                desc(DiagnosticModelRun.created_at),
                desc(DiagnosticModelRun.id),
            )
            .limit(1)
        ).scalar_one_or_none()

        if run is None:
            raise HTTPException(
                status_code=503,
                detail="No persisted trained diagnostic run is available",
            )

    prediction_count = int(
        db.scalar(
            select(func.count(DiagnosticPrediction.id)).where(
                DiagnosticPrediction.run_id == run.id,
                DiagnosticPrediction.experiment_id == run.experiment_id,
            )
        )
        or 0
    )

    if prediction_count < 1:
        status_code = 409 if run_id is not None else 503
        raise HTTPException(
            status_code=status_code,
            detail=(
                f"Diagnostic run {run.id} has no persisted operational "
                "predictions"
            ),
        )

    return run.experiment_id, run


def _current_vehicle_twin_record(
    db: Session,
    vehicle_id: str,
    *,
    selected_run: DiagnosticModelRun | None = None,
):
    if selected_run is None:
        experiment_id, run = _resolve_vehicle_twin_run(db)
    else:
        run = selected_run
        experiment_id = run.experiment_id

    _, decision_run, decisions = _current_fleet_decision_records(
        db,
        selected_run=run,
    )
    if decision_run.id != run.id:
        raise HTTPException(status_code=409, detail="Fleet decision state is not aligned to the current run")
    decision = next((r for r in decisions if r["vehicleId"] == vehicle_id), None)
    if decision is None:
        raise HTTPException(status_code=404, detail="Vehicle is not present in current operational twin population")

    prediction = db.execute(select(DiagnosticPrediction).where(
        DiagnosticPrediction.run_id == run.id,
        DiagnosticPrediction.experiment_id == experiment_id,
        DiagnosticPrediction.vehicle_id == vehicle_id,
    ).limit(1)).scalar_one_or_none()
    if prediction is None:
        raise HTTPException(status_code=404, detail="Current-run prediction unavailable for vehicle twin")

    scoring_context = db.execute(
        select(Telemetry)
        .where(
            Telemetry.experiment_id == experiment_id,
            Telemetry.vehicle_id == vehicle_id,
            Telemetry.timestamp <= prediction.anchor_timestamp,
        )
        .order_by(
            desc(Telemetry.timestamp),
            desc(Telemetry.id),
        )
        .limit(1)
    ).scalar_one_or_none()

    episode = None
    if decision.get("episodeId") is not None:
        episode = db.execute(select(DiagnosticEpisode).where(
            DiagnosticEpisode.id == int(decision["episodeId"]),
            DiagnosticEpisode.run_id == run.id,
            DiagnosticEpisode.experiment_id == experiment_id,
        ).limit(1)).scalar_one_or_none()

    case = None
    if decision.get("caseId") is not None:
        case = db.execute(select(DiagnosticCase).where(
            DiagnosticCase.id == int(decision["caseId"]),
            DiagnosticCase.run_id == run.id,
            DiagnosticCase.experiment_id == experiment_id,
        ).limit(1)).scalar_one_or_none()

    plan = None
    watch = None
    if case is not None:
        plan = db.execute(select(DiagnosticMaintenancePlan).where(
            DiagnosticMaintenancePlan.run_id == run.id,
            DiagnosticMaintenancePlan.experiment_id == experiment_id,
            DiagnosticMaintenancePlan.case_id == case.id,
        ).limit(1)).scalar_one_or_none()
        watch = db.execute(select(DiagnosticWatchlistEntry).where(
            DiagnosticWatchlistEntry.run_id == run.id,
            DiagnosticWatchlistEntry.experiment_id == experiment_id,
            DiagnosticWatchlistEntry.case_id == case.id,
        ).limit(1)).scalar_one_or_none()

    actions = db.execute(select(DiagnosticAutomationAction).where(
        DiagnosticAutomationAction.run_id == run.id,
        DiagnosticAutomationAction.experiment_id == experiment_id,
        DiagnosticAutomationAction.vehicle_id == vehicle_id,
    ).order_by(DiagnosticAutomationAction.id)).scalars().all()
    statuses = sorted({a.status for a in actions})

    fleet_links = []
    fleet_snaps = db.execute(select(DiagnosticFleetDecisionSnapshot).where(
        DiagnosticFleetDecisionSnapshot.run_id == run.id,
        DiagnosticFleetDecisionSnapshot.experiment_id == experiment_id,
    ).order_by(DiagnosticFleetDecisionSnapshot.created_at)).scalars().all()
    for snap in fleet_snaps:
        if any(isinstance(r, dict) and r.get("vehicleId") == vehicle_id for r in _json_list(snap.records_json)):
            fleet_links.append({
                "snapshotId": snap.id, "createdAt": snap.created_at.isoformat(),
                "label": snap.label, "stateHash": snap.state_hash,
            })

    twin = {
        "vehicleId": vehicle_id, "runId": run.id, "experimentId": experiment_id,
        "lineage": run.lineage, "rulesVersion": VEHICLE_TWIN_RULES_VERSION,
        "vehicleContext": {
            "model": scoring_context.model if scoring_context else None,
            "factory": scoring_context.factory if scoring_context else None,
            "firmware": scoring_context.firmware if scoring_context else None,
            "pumpRevision": scoring_context.pump_revision if scoring_context else None,
            "scoringContextMileage": (
                round(float(scoring_context.mileage), 1)
                if scoring_context
                else None
            ),
            "scoringContextTimestamp": (
                scoring_context.timestamp.isoformat()
                if scoring_context
                else None
            ),
        },
        "modelState": {
            "predictionId": prediction.id, "topClass": prediction.top_class,
            "topConfidence": round(float(prediction.top_confidence), 6),
            "anchorTimestamp": prediction.anchor_timestamp.isoformat(),
            "anchorMileage": round(float(prediction.anchor_mileage), 1),
            "hypotheses": _json_list(prediction.hypotheses_json),
            "observableEvidence": _json_list(prediction.evidence_json),
            "champion": run.champion,
        },
        "diagnosticState": {
            "episodeId": episode.id if episode else None,
            "hypothesisClass": episode.hypothesis_class if episode else None,
            "episodeState": episode.state if episode else None,
            "isOpen": bool(episode.is_open) if episode else None,
            "leftCensored": bool(episode.left_censored) if episode else None,
            "startTimestamp": episode.start_timestamp.isoformat() if episode else None,
            "startMileage": round(float(episode.start_mileage), 1) if episode else None,
            "latestTimestamp": episode.end_timestamp.isoformat() if episode else None,
            "latestMileage": round(float(episode.end_mileage), 1) if episode else None,
            "eventCount": int(episode.event_count) if episode else 0,
            "latestConfidence": round(float(episode.latest_confidence), 6) if episode and episode.latest_confidence is not None else None,
        },
        "caseState": {
            "caseId": case.id if case else None, "status": case.status if case else None,
            "reviewPriority": case.review_priority if case else None,
            "assignedTo": case.assigned_to if case else None,
            "noteCount": int(case.note_count) if case else 0,
            "watchlisted": watch is not None,
            "watchlistEntryId": watch.id if watch else None,
        },
        "prognosticState": {
            "maintenanceTier": decision.get("maintenanceTier"),
            "priorityScore": decision.get("priorityScore"),
            "recommendedReviewWindow": decision.get("recommendedReviewWindow"),
            "trajectoryEligible": decision.get("trajectoryEligible"),
        },
        "maintenanceState": {
            "planId": plan.id if plan else None, "state": plan.state if plan else None,
            "owner": plan.owner if plan else None,
            "targetMileage": round(float(plan.target_mileage), 1) if plan and plan.target_mileage is not None else None,
            "updatedAt": plan.updated_at.isoformat() if plan else None,
        },
        "automationState": {
            "actionIds": [a.id for a in actions], "statuses": statuses,
            "currentStatus": current_automation_status(statuses),
            "pendingActionTypes": sorted({a.action_type for a in actions if a.status == AUTOMATION_STATUS_PENDING_APPROVAL}),
            "actions": [{
                "id": a.id, "policyKey": a.policy_key, "status": a.status,
                "severity": a.severity, "actionType": a.action_type,
                "createdAt": a.created_at.isoformat(),
            } for a in actions],
        },
        "fleetDecisionState": {
            "decisionState": decision.get("decisionState"),
            "attentionScore": decision.get("attentionScore"),
            "workloadUnits": decision.get("workloadUnits"),
        },
        "coverageState": {
            "coverageGaps": list(decision.get("coverageGaps") or []),
            "coverageGapCount": len(decision.get("coverageGaps") or []),
        },
        "fleetSnapshotLinks": fleet_links,
        "sourceVersions": {
            "twinRules": VEHICLE_TWIN_RULES_VERSION,
            "modelLineage": run.lineage,
            "eventRules": episode.source_event_rules_version if episode else None,
            "episodeRules": episode.rules_version if episode else None,
            "caseRules": case.rules_version if case else None,
            "prognosticRules": plan.rules_version if plan else PROGNOSTIC_RULES_VERSION,
            "automationRules": AUTOMATION_RULES_VERSION,
            "fleetDecisionRules": FLEET_DECISION_RULES_VERSION,
        },
    }
    twin["layerPresence"] = layer_presence_payload(twin)
    return experiment_id, run, twin


def _vehicle_twin_timeline_items(db: Session, experiment_id: str, run, vehicle_id: str) -> list[dict]:
    items = []

    # The persisted DiagnosticPrediction is the authoritative scoring snapshot
    # for this run. Replay rows may have been reconstructed later from
    # observable, anchor-bounded telemetry and can therefore differ numerically.
    prediction = db.execute(
        select(DiagnosticPrediction).where(
            DiagnosticPrediction.run_id == run.id,
            DiagnosticPrediction.experiment_id == experiment_id,
            DiagnosticPrediction.vehicle_id == vehicle_id,
        ).limit(1)
    ).scalar_one_or_none()

    if prediction is not None:
        items.append({
            "id": f"prediction-{prediction.id}",
            "layer": "MODEL",
            "type": "CANONICAL_PREDICTION",
            "timestamp": prediction.anchor_timestamp.isoformat(),
            "mileage": round(float(prediction.anchor_mileage), 1),
            "title": f"Canonical prediction: {prediction.top_class}",
            "detail": (
                f"Top confidence {float(prediction.top_confidence):.3f} · "
                "persisted scoring snapshot"
            ),
        })

    replay = db.execute(
        select(DiagnosticReplayPoint).where(
            DiagnosticReplayPoint.run_id == run.id,
            DiagnosticReplayPoint.experiment_id == experiment_id,
            DiagnosticReplayPoint.vehicle_id == vehicle_id,
        ).order_by(
            DiagnosticReplayPoint.anchor_timestamp,
            DiagnosticReplayPoint.id,
        )
    ).scalars().all()

    prev = None
    for i, point in enumerate(replay):
        if (
            i == 0
            or i == len(replay) - 1
            or point.top_class != prev
        ):
            items.append({
                "id": f"replay-{point.id}",
                "layer": "MODEL",
                "type": "REPLAY_STATE",
                "timestamp": point.anchor_timestamp.isoformat(),
                "mileage": round(float(point.anchor_mileage), 1),
                "title": f"Replay reconstruction: {point.top_class}",
                "detail": (
                    f"Top confidence {float(point.top_confidence):.3f} · "
                    "reconstructed observable history"
                ),
            })

        prev = point.top_class

    for e in db.execute(select(DiagnosticEvent).where(
        DiagnosticEvent.run_id == run.id, DiagnosticEvent.experiment_id == experiment_id,
        DiagnosticEvent.vehicle_id == vehicle_id,
    ).order_by(DiagnosticEvent.anchor_timestamp, DiagnosticEvent.id)).scalars().all():
        items.append({"id": f"event-{e.id}", "layer":"DIAGNOSTIC", "type":e.event_type,
            "timestamp":e.anchor_timestamp.isoformat(), "mileage":round(float(e.anchor_mileage),1),
            "title":e.event_type.replace("_"," ").title(),
            "detail":f"{e.previous_class or '—'} → {e.current_class or '—'}"})

    for ep in db.execute(select(DiagnosticEpisode).where(
        DiagnosticEpisode.run_id == run.id, DiagnosticEpisode.experiment_id == experiment_id,
        DiagnosticEpisode.vehicle_id == vehicle_id,
    ).order_by(DiagnosticEpisode.start_timestamp)).scalars().all():
        items.append({"id":f"episode-{ep.id}","layer":"DIAGNOSTIC","type":"EPISODE_STARTED",
            "timestamp":ep.start_timestamp.isoformat(),"mileage":round(float(ep.start_mileage),1),
            "title":f"{ep.hypothesis_class} episode","detail":f"State {ep.state}"})

    for c in db.execute(select(DiagnosticCase).where(
        DiagnosticCase.run_id == run.id, DiagnosticCase.experiment_id == experiment_id,
        DiagnosticCase.vehicle_id == vehicle_id,
    ).order_by(DiagnosticCase.created_at)).scalars().all():
        items.append({"id":f"case-{c.id}","layer":"CASE","type":"CASE_CREATED",
            "timestamp":c.created_at.isoformat(),"mileage":round(float(c.start_mileage),1),
            "title":f"Case #{c.id} created","detail":f"{c.review_priority} · {c.status}"})

    for a in db.execute(select(DiagnosticCaseActivity).where(
        DiagnosticCaseActivity.run_id == run.id, DiagnosticCaseActivity.experiment_id == experiment_id,
        DiagnosticCaseActivity.vehicle_id == vehicle_id,
    ).order_by(DiagnosticCaseActivity.created_at)).scalars().all():
        items.append({"id":f"case-activity-{a.id}","layer":"CASE","type":a.activity_type,
            "timestamp":a.created_at.isoformat(),"mileage":None,"title":a.activity_type.replace("_"," ").title(),
            "detail":a.note_text or f"{a.from_value or '—'} → {a.to_value or '—'}"})

    for w in db.execute(select(DiagnosticWatchlistEntry).where(
        DiagnosticWatchlistEntry.run_id == run.id, DiagnosticWatchlistEntry.experiment_id == experiment_id,
        DiagnosticWatchlistEntry.vehicle_id == vehicle_id,
    ).order_by(DiagnosticWatchlistEntry.created_at)).scalars().all():
        items.append({"id":f"watch-{w.id}","layer":"CASE","type":"WATCHLIST_ADDED",
            "timestamp":w.created_at.isoformat(),"mileage":None,"title":"Added to watchlist","detail":w.note or f"Actor {w.actor}"})

    for a in db.execute(select(DiagnosticMaintenanceActivity).where(
        DiagnosticMaintenanceActivity.run_id == run.id, DiagnosticMaintenanceActivity.experiment_id == experiment_id,
        DiagnosticMaintenanceActivity.vehicle_id == vehicle_id,
    ).order_by(DiagnosticMaintenanceActivity.created_at)).scalars().all():
        items.append({"id":f"maint-{a.id}","layer":"MAINTENANCE","type":a.activity_type,
            "timestamp":a.created_at.isoformat(),"mileage":None,"title":a.activity_type.replace("_"," ").title(),
            "detail":a.note_text or f"{a.from_value or '—'} → {a.to_value or '—'}"})

    for a in db.execute(select(DiagnosticAutomationActivity).where(
        DiagnosticAutomationActivity.run_id == run.id, DiagnosticAutomationActivity.experiment_id == experiment_id,
        DiagnosticAutomationActivity.vehicle_id == vehicle_id,
    ).order_by(DiagnosticAutomationActivity.created_at)).scalars().all():
        items.append({"id":f"auto-{a.id}","layer":"AUTOMATION","type":a.activity_type,
            "timestamp":a.created_at.isoformat(),"mileage":None,"title":a.activity_type.replace("_"," ").title(),
            "detail":a.note_text or f"Actor {a.actor}"})

    for s in db.execute(select(DiagnosticFleetDecisionSnapshot).where(
        DiagnosticFleetDecisionSnapshot.run_id == run.id,
        DiagnosticFleetDecisionSnapshot.experiment_id == experiment_id,
    ).order_by(DiagnosticFleetDecisionSnapshot.created_at)).scalars().all():
        if any(isinstance(r,dict) and r.get("vehicleId") == vehicle_id for r in _json_list(s.records_json)):
            items.append({"id":f"fleet-snap-{s.id}","layer":"FLEET_DECISION","type":"FLEET_STATE_CHECKPOINT",
                "timestamp":s.created_at.isoformat(),"mileage":None,"title":s.label or f"Fleet snapshot #{s.id}","detail":s.state_hash})
    items.sort(key=lambda x:(x["timestamp"],x["id"]))
    return items


@router.get("/twins/summary")
def vehicle_twins_summary(
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _resolve_vehicle_twin_run(db, run_id)
    _, _, records = _current_fleet_decision_records(
        db,
        selected_run=run,
    )
    rows = [twin_list_record(r) for r in records]
    snapshot_count = int(db.scalar(select(func.count(DiagnosticVehicleTwinSnapshot.id)).where(
        DiagnosticVehicleTwinSnapshot.run_id == run.id,
        DiagnosticVehicleTwinSnapshot.experiment_id == experiment_id,
    )) or 0)
    return {
        "runId":run.id,"experimentId":experiment_id,"lineage":run.lineage,
        "rulesVersion":VEHICLE_TWIN_RULES_VERSION,"totalTwins":len(rows),
        "twinsWithEpisodes":sum(1 for r in rows if r["episodeId"] is not None),
        "twinsWithCases":sum(1 for r in rows if r["caseId"] is not None),
        "twinsWithMaintenancePlans":sum(1 for r in rows if r["maintenancePlanState"] is not None),
        "twinsWithAutomation":sum(1 for r in rows if r["automationStatus"] is not None),
        "twinsWithCoverageGaps":sum(1 for r in rows if r["coverageGaps"]),
        "persistedTwinSnapshots":snapshot_count,
        "byDecisionState":[{"state":s,"twins":sum(1 for r in rows if r["decisionState"]==s)} for s in DECISION_STATES],
        "scopePolicy":_vehicle_twin_scope_policy(),
        "interpretationPolicy":"Operational twin, not a validated physics-based digital twin or proof of component condition.",
        "generatedAt":datetime.now(timezone.utc).isoformat(),
    }


@router.get("/twins")
def vehicle_twins(limit:int=Query(default=100,ge=1,le=500), decision_state:str|None=None,
                  hypothesis_class:str|None=None, gap:str|None=None,
                  run_id:int|None=Query(default=None,ge=1),
                  db:Session=Depends(db_session)) -> dict:
    experiment_id, run = _resolve_vehicle_twin_run(db, run_id)
    _, _, records = _current_fleet_decision_records(
        db,
        selected_run=run,
    )
    rows=[twin_list_record(r) for r in records]
    if decision_state:
        if decision_state not in DECISION_STATES: raise HTTPException(422, detail="Unsupported decision state")
        rows=[r for r in rows if r["decisionState"]==decision_state]
    if hypothesis_class: rows=[r for r in rows if r["topClass"]==hypothesis_class]
    if gap:
        if gap not in COVERAGE_GAPS: raise HTTPException(422, detail="Unsupported coverage gap")
        rows=[r for r in rows if gap in r["coverageGaps"]]
    rows.sort(key=lambda r:(float(r.get("attentionScore") or 0),float(r.get("topConfidence") or 0),r["vehicleId"]),reverse=True)
    return {"runId":run.id,"experimentId":experiment_id,"rulesVersion":VEHICLE_TWIN_RULES_VERSION,
            "totalMatched":len(rows),"returned":min(limit,len(rows)),"twins":rows[:limit],"scopePolicy":_vehicle_twin_scope_policy()}


@router.get("/twins/compare")
def compare_vehicle_twins(vehicle_ids:str=Query(min_length=1),
                          run_id:int|None=Query(default=None,ge=1),
                          db:Session=Depends(db_session)) -> dict:
    ids=list(dict.fromkeys(v.strip() for v in vehicle_ids.split(",") if v.strip()))
    if len(ids)<2 or len(ids)>4: raise HTTPException(422,detail="Provide between 2 and 4 comma-separated vehicle IDs")
    _, run = _resolve_vehicle_twin_run(db, run_id)
    twins=[
        _current_vehicle_twin_record(
            db,
            v,
            selected_run=run,
        )[2]
        for v in ids
    ]
    return {"rulesVersion":VEHICLE_TWIN_RULES_VERSION,"referenceVehicleId":twins[0]["vehicleId"],
            "vehicles":twins,"comparisons":[compare_twin_states(twins[0],t) for t in twins[1:]],
            "scopePolicy":_vehicle_twin_scope_policy(),
            "interpretationPolicy":"Twin comparison is deterministic operational-state differencing, not physical similarity or shared-failure probability."}


@router.get("/twins/{vehicle_id}")
def vehicle_twin_detail(vehicle_id:str,
                        run_id:int|None=Query(default=None,ge=1),
                        db:Session=Depends(db_session)) -> dict:
    _, run = _resolve_vehicle_twin_run(db, run_id)
    experiment_id, run, twin = _current_vehicle_twin_record(
        db,
        vehicle_id,
        selected_run=run,
    )
    twin["persistedTwinSnapshots"] = int(db.scalar(select(func.count(DiagnosticVehicleTwinSnapshot.id)).where(
        DiagnosticVehicleTwinSnapshot.run_id==run.id,
        DiagnosticVehicleTwinSnapshot.experiment_id==experiment_id,
        DiagnosticVehicleTwinSnapshot.vehicle_id==vehicle_id,
    )) or 0)
    twin["scopePolicy"]=_vehicle_twin_scope_policy()
    twin["interpretationPolicy"]="Unified current-run operational evidence; not private failure truth or a physics-based digital twin."
    twin["generatedAt"]=datetime.now(timezone.utc).isoformat()
    return twin


@router.get("/twins/{vehicle_id}/timeline")
def vehicle_twin_timeline(vehicle_id:str,
                          limit:int=Query(default=200,ge=1,le=500),
                          run_id:int|None=Query(default=None,ge=1),
                          db:Session=Depends(db_session)) -> dict:
    _, run = _resolve_vehicle_twin_run(db, run_id)
    experiment_id, run, _ = _current_vehicle_twin_record(
        db,
        vehicle_id,
        selected_run=run,
    )
    items=_vehicle_twin_timeline_items(db,experiment_id,run,vehicle_id)
    selected=items[-limit:]
    return {"runId":run.id,"experimentId":experiment_id,"vehicleId":vehicle_id,"rulesVersion":VEHICLE_TWIN_RULES_VERSION,
            "totalItems":len(items),"returned":len(selected),"items":selected,"scopePolicy":_vehicle_twin_scope_policy(),
            "interpretationPolicy":"Merged operational chronology. CANONICAL_PREDICTION is the persisted run scoring snapshot; REPLAY_STATE entries are observable-history reconstructions and may differ numerically at the same anchor. Sequence does not imply physical causality."}


@router.get("/twins/{vehicle_id}/graph")
def vehicle_twin_graph(vehicle_id:str,
                       run_id:int|None=Query(default=None,ge=1),
                       db:Session=Depends(db_session)) -> dict:
    _, run = _resolve_vehicle_twin_run(db, run_id)
    experiment_id, run, t = _current_vehicle_twin_record(
        db,
        vehicle_id,
        selected_run=run,
    )
    m,d,c,p,ma,a,f,cv=(t["modelState"],t["diagnosticState"],t["caseState"],t["prognosticState"],t["maintenanceState"],t["automationState"],t["fleetDecisionState"],t["coverageState"])
    nodes=[
        {"id":"model","layer":"MODEL","label":m.get("topClass"),"present":True},
        {"id":"episode","layer":"DIAGNOSTIC","label":d.get("episodeState"),"present":d.get("episodeId") is not None},
        {"id":"case","layer":"CASE","label":c.get("status"),"present":c.get("caseId") is not None},
        {"id":"prognostic","layer":"PROGNOSTIC","label":p.get("maintenanceTier"),"present":p.get("maintenanceTier") is not None},
        {"id":"maintenance","layer":"MAINTENANCE","label":ma.get("state"),"present":ma.get("planId") is not None},
        {"id":"automation","layer":"AUTOMATION","label":a.get("currentStatus"),"present":bool(a.get("actionIds"))},
        {"id":"fleet-decision","layer":"FLEET_DECISION","label":f.get("decisionState"),"present":True},
        {"id":"coverage","layer":"COVERAGE","label":f'{cv.get("coverageGapCount",0)} gaps',"present":True},
    ]
    present={n["id"]:n["present"] for n in nodes}
    candidates=[("model","episode","TEMPORALIZED_AS"),("episode","case","OPERATIONALIZED_AS"),("case","prognostic","REVIEWED_BY"),
                ("prognostic","maintenance","INFORMS"),("prognostic","automation","EVALUATED_BY"),("maintenance","fleet-decision","SYNTHESIZED_IN"),
                ("automation","fleet-decision","SYNTHESIZED_IN"),("fleet-decision","coverage","ASSESSED_FOR")]
    edges=[{"from":x,"to":y,"relation":r} for x,y,r in candidates if present.get(x) and present.get(y)]
    return {"runId":run.id,"experimentId":experiment_id,"vehicleId":vehicle_id,"rulesVersion":VEHICLE_TWIN_RULES_VERSION,
            "nodes":nodes,"edges":edges,"interpretationPolicy":"This graph is data/workflow lineage, not a causal component graph or physical dependency proof."}


@router.get("/twins/{vehicle_id}/evidence")
def vehicle_twin_evidence(vehicle_id:str,
                          run_id:int|None=Query(default=None,ge=1),
                          db:Session=Depends(db_session)) -> dict:
    _, run = _resolve_vehicle_twin_run(db, run_id)
    experiment_id, run, t = _current_vehicle_twin_record(
        db,
        vehicle_id,
        selected_run=run,
    )
    replay=int(db.scalar(select(func.count(DiagnosticReplayPoint.id)).where(DiagnosticReplayPoint.run_id==run.id,DiagnosticReplayPoint.experiment_id==experiment_id,DiagnosticReplayPoint.vehicle_id==vehicle_id)) or 0)
    events=int(db.scalar(select(func.count(DiagnosticEvent.id)).where(DiagnosticEvent.run_id==run.id,DiagnosticEvent.experiment_id==experiment_id,DiagnosticEvent.vehicle_id==vehicle_id)) or 0)
    return {"runId":run.id,"experimentId":experiment_id,"vehicleId":vehicle_id,"rulesVersion":VEHICLE_TWIN_RULES_VERSION,
            "observableModelEvidence":t["modelState"]["observableEvidence"],
            "counts":{"replayPoints":replay,"diagnosticEvents":events,"episodes":1 if t["diagnosticState"]["episodeId"] else 0,
                      "cases":1 if t["caseState"]["caseId"] else 0,"maintenancePlans":1 if t["maintenanceState"]["planId"] else 0,
                      "automationActions":len(t["automationState"]["actionIds"]),"fleetSnapshotLinks":len(t["fleetSnapshotLinks"])},
            "sourceVersions":t["sourceVersions"],
            "truthBoundary":{"usesPrivateFailureTruth":False,"failureMarkersExposed":False,
                             "operationalModelHypothesesAreFailureTruth":False,"observedSignalsAreCausalAttribution":False},
            "interpretationPolicy":"Observable/persisted evidence inventory; private simulated failure truth is deliberately excluded."}


@router.post("/twins/{vehicle_id}/snapshots")
def create_vehicle_twin_snapshot(vehicle_id:str,
                                 request:VehicleTwinSnapshotCreate,
                                 run_id:int|None=Query(default=None,ge=1),
                                 db:Session=Depends(db_session)) -> dict:
    _, run = _resolve_vehicle_twin_run(db, run_id)
    experiment_id, run, twin = _current_vehicle_twin_record(
        db,
        vehicle_id,
        selected_run=run,
    )
    canonical=canonical_twin_state(twin)
    raw=json.dumps(canonical,sort_keys=True,separators=(",",":"))
    state_hash=hashlib.sha256(raw.encode()).hexdigest()
    existing=db.execute(select(DiagnosticVehicleTwinSnapshot).where(
        DiagnosticVehicleTwinSnapshot.run_id==run.id,DiagnosticVehicleTwinSnapshot.experiment_id==experiment_id,
        DiagnosticVehicleTwinSnapshot.vehicle_id==vehicle_id,DiagnosticVehicleTwinSnapshot.rules_version==VEHICLE_TWIN_RULES_VERSION,
        DiagnosticVehicleTwinSnapshot.state_hash==state_hash).limit(1)).scalar_one_or_none()
    if existing:
        return {"created":False,"snapshot":_vehicle_twin_snapshot_payload(existing),
                "interpretationPolicy":"Identical operational twin state already has a checkpoint. No diagnostic or workflow evidence was modified."}
    row=DiagnosticVehicleTwinSnapshot(run_id=run.id,experiment_id=experiment_id,vehicle_id=vehicle_id,
        rules_version=VEHICLE_TWIN_RULES_VERSION,created_at=datetime.now(timezone.utc),actor=request.actor,
        label=request.label.strip() if request.label and request.label.strip() else None,state_hash=state_hash,twin_json=raw)
    db.add(row); db.commit(); db.refresh(row)
    return {"created":True,"snapshot":_vehicle_twin_snapshot_payload(row),"scopePolicy":_vehicle_twin_scope_policy(),
            "interpretationPolicy":"Twin snapshots persist derived operational state only. They do not rewrite predictions, replay, events, episodes, cases, maintenance, automation, fleet-decision evidence, model artifacts, benchmark evidence, or private failure truth."}


@router.get("/twins/{vehicle_id}/snapshots")
def vehicle_twin_snapshots(vehicle_id:str,
                           limit:int=Query(default=20,ge=1,le=100),
                           run_id:int|None=Query(default=None,ge=1),
                           db:Session=Depends(db_session)) -> dict:
    _, run = _resolve_vehicle_twin_run(db, run_id)
    experiment_id, run, _ = _current_vehicle_twin_record(
        db,
        vehicle_id,
        selected_run=run,
    )
    total=int(db.scalar(select(func.count(DiagnosticVehicleTwinSnapshot.id)).where(DiagnosticVehicleTwinSnapshot.run_id==run.id,DiagnosticVehicleTwinSnapshot.experiment_id==experiment_id,DiagnosticVehicleTwinSnapshot.vehicle_id==vehicle_id)) or 0)
    rows=db.execute(select(DiagnosticVehicleTwinSnapshot).where(DiagnosticVehicleTwinSnapshot.run_id==run.id,DiagnosticVehicleTwinSnapshot.experiment_id==experiment_id,DiagnosticVehicleTwinSnapshot.vehicle_id==vehicle_id).order_by(desc(DiagnosticVehicleTwinSnapshot.created_at),desc(DiagnosticVehicleTwinSnapshot.id)).limit(limit)).scalars().all()
    return {"runId":run.id,"experimentId":experiment_id,"vehicleId":vehicle_id,"rulesVersion":VEHICLE_TWIN_RULES_VERSION,
            "total":total,"returned":len(rows),"snapshots":[_vehicle_twin_snapshot_payload(r) for r in rows],"scopePolicy":_vehicle_twin_scope_policy()}


# Phase 7.2 — Fleet Twin + Normalized Cohort Exposure
#
# Fleet Twin exposure is a selected-run operational population view.
# Counts describe operational volume; normalized rates use cohort population
# denominators. Rate ratios are descriptive representation only — not physical
# failure risk, reliability probability, causal inference, RUL, or attribution.


def _fleet_twin_scope_policy() -> dict:
    return {
        "selectedRunOnly": True,
        "defaultRunSelection": "latest_persisted_trained_run",
        "activeTelemetryExperimentRequired": False,
        "exactExperimentOnly": True,
        "scoringContextBoundedToPredictionAnchor": True,
        "postRunTelemetryUsed": False,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "physicalRiskScore": False,
        "physicalFailureProbability": False,
        "relativeFailureRisk": False,
        "physicalRul": False,
        "causalInference": False,
        "modelFeatureAttribution": False,
        "technicianHours": False,
        "modelRetrained": False,
        "benchmarkModified": False,
    }


def _fleet_twin_scoring_context_by_vehicle(
    db: Session,
    *,
    experiment_id: str,
    run: DiagnosticModelRun,
) -> dict[str, dict]:
    """
    Resolve frozen cohort metadata for the selected run in one SQL query.

    Each vehicle uses the latest observable telemetry row whose timestamp is
    less than or equal to that vehicle's persisted prediction anchor. This is
    the same scoring-context boundary used by the Phase 7.1 vehicle twin.

    The window function prevents a 500-vehicle N+1 query pattern.
    """

    ranked = (
        select(
            DiagnosticPrediction.vehicle_id.label("vehicle_id"),
            Telemetry.model.label("model"),
            Telemetry.factory.label("factory"),
            Telemetry.firmware.label("firmware"),
            Telemetry.pump_revision.label("pump_revision"),
            Telemetry.mileage.label("mileage"),
            Telemetry.timestamp.label("timestamp"),
            func.row_number()
            .over(
                partition_by=DiagnosticPrediction.vehicle_id,
                order_by=(
                    desc(Telemetry.timestamp),
                    desc(Telemetry.id),
                ),
            )
            .label("row_number"),
        )
        .join(
            Telemetry,
            (
                (Telemetry.experiment_id == DiagnosticPrediction.experiment_id)
                & (Telemetry.vehicle_id == DiagnosticPrediction.vehicle_id)
                & (Telemetry.timestamp <= DiagnosticPrediction.anchor_timestamp)
            ),
        )
        .where(
            DiagnosticPrediction.run_id == run.id,
            DiagnosticPrediction.experiment_id == experiment_id,
        )
        .subquery()
    )

    rows = db.execute(
        select(
            ranked.c.vehicle_id,
            ranked.c.model,
            ranked.c.factory,
            ranked.c.firmware,
            ranked.c.pump_revision,
            ranked.c.mileage,
            ranked.c.timestamp,
        )
        .where(ranked.c.row_number == 1)
        .order_by(ranked.c.vehicle_id)
    ).all()

    return {
        str(row.vehicle_id): {
            "model": row.model,
            "factory": row.factory,
            "firmware": row.firmware,
            "pumpRevision": row.pump_revision,
            "scoringContextMileage": (
                round(float(row.mileage), 1)
                if row.mileage is not None
                else None
            ),
            "scoringContextTimestamp": (
                row.timestamp.isoformat()
                if row.timestamp is not None
                else None
            ),
        }
        for row in rows
    }


def _current_fleet_twin_records(
    db: Session,
    *,
    run_id: int | None = None,
) -> tuple[str, DiagnosticModelRun, list[dict]]:
    experiment_id, run = _resolve_vehicle_twin_run(db, run_id)

    _, decision_run, decision_records = _current_fleet_decision_records(
        db,
        selected_run=run,
    )

    if decision_run.id != run.id:
        raise HTTPException(
            status_code=409,
            detail="Fleet decision records are not aligned to selected twin run",
        )

    contexts = _fleet_twin_scoring_context_by_vehicle(
        db,
        experiment_id=experiment_id,
        run=run,
    )

    records: list[dict] = []

    for decision in decision_records:
        vehicle_id = str(decision["vehicleId"])
        context = contexts.get(vehicle_id, {})

        records.append(
            {
                **decision,
                "model": context.get("model"),
                "factory": context.get("factory"),
                "firmware": context.get("firmware"),
                "pumpRevision": context.get("pumpRevision"),
                "scoringContextMileage": context.get(
                    "scoringContextMileage"
                ),
                "scoringContextTimestamp": context.get(
                    "scoringContextTimestamp"
                ),
                "automationStatus": current_automation_status(
                    list(decision.get("automationStatuses") or [])
                ),
            }
        )

    records.sort(key=lambda row: str(row["vehicleId"]))

    return experiment_id, run, records


@router.get("/fleet-twin/summary")
def fleet_twin_summary(
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = _current_fleet_twin_records(
        db,
        run_id=run_id,
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": FLEET_TWIN_RULES_VERSION,
        **fleet_exposure_summary(records),
        "dimensions": list(FLEET_TWIN_DIMENSIONS),
        "exposureMeasures": list(FLEET_TWIN_EXPOSURE_MEASURES),
        "scopePolicy": _fleet_twin_scope_policy(),
        "interpretationPolicy": (
            "Fleet Twin counts describe selected-run operational volume. "
            "Rates normalize by cohort population. Workload units are synthetic "
            "workflow prioritization units, not technician hours. Exposure "
            "rates and ratios are not physical failure probabilities, relative "
            "failure risk, reliability estimates, causal effects, RUL, or "
            "model attribution."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/fleet-twin/cohorts")
def fleet_twin_cohorts(
    dimension: str = Query(default="factory"),
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    if dimension not in FLEET_TWIN_DIMENSIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported Fleet Twin cohort dimension",
                "allowed": list(FLEET_TWIN_DIMENSIONS),
            },
        )

    experiment_id, run, records = _current_fleet_twin_records(
        db,
        run_id=run_id,
    )

    payload = fleet_cohort_exposure(records, dimension)

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        **payload,
        "scopePolicy": _fleet_twin_scope_policy(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/fleet-twin/exposure")
def fleet_twin_exposure(
    dimension: str = Query(default="factory"),
    measure: str = Query(default="nonHealthy"),
    limit: int = Query(default=50, ge=1, le=500),
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    if dimension not in FLEET_TWIN_DIMENSIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported Fleet Twin cohort dimension",
                "allowed": list(FLEET_TWIN_DIMENSIONS),
            },
        )

    if measure not in FLEET_TWIN_EXPOSURE_MEASURES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported Fleet Twin exposure measure",
                "allowed": list(FLEET_TWIN_EXPOSURE_MEASURES),
            },
        )

    experiment_id, run, records = _current_fleet_twin_records(
        db,
        run_id=run_id,
    )

    rows = cohort_exposure_rows(records, dimension)

    rows.sort(
        key=lambda row: (
            exposure_measure_rate(row, measure),
            int(row.get("populationCount") or 0),
            str(row.get("value") or ""),
        ),
        reverse=True,
    )

    selected = rows[:limit]

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": FLEET_TWIN_RULES_VERSION,
        "dimension": dimension,
        "measure": measure,
        "fleetBaseline": fleet_exposure_summary(records),
        "totalCohorts": len(rows),
        "returnedCohorts": len(selected),
        "cohorts": selected,
        "scopePolicy": _fleet_twin_scope_policy(),
        "interpretationPolicy": (
            "Ranking uses normalized operational cohort rate, not raw count. "
            "Higher representation does not establish greater physical failure "
            "risk, reliability risk, causality, or component condition."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/fleet-twin/exposure/compare")
def fleet_twin_exposure_compare(
    dimension: str = Query(),
    reference_value: str = Query(min_length=1),
    candidate_value: str = Query(min_length=1),
    measure: str = Query(default="nonHealthy"),
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    if dimension not in FLEET_TWIN_DIMENSIONS:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported Fleet Twin cohort dimension",
                "allowed": list(FLEET_TWIN_DIMENSIONS),
            },
        )

    if measure not in FLEET_TWIN_EXPOSURE_MEASURES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported Fleet Twin exposure measure",
                "allowed": list(FLEET_TWIN_EXPOSURE_MEASURES),
            },
        )

    experiment_id, run, records = _current_fleet_twin_records(
        db,
        run_id=run_id,
    )

    rows = cohort_exposure_rows(records, dimension)
    by_value = {
        str(row["value"]): row
        for row in rows
    }

    if reference_value not in by_value:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Reference cohort {reference_value!r} was not found "
                f"for dimension {dimension!r}"
            ),
        )

    if candidate_value not in by_value:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Candidate cohort {candidate_value!r} was not found "
                f"for dimension {dimension!r}"
            ),
        )

    comparison = compare_cohort_exposure(
        by_value[reference_value],
        by_value[candidate_value],
        measure=measure,
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": FLEET_TWIN_RULES_VERSION,
        "comparison": comparison,
        "scopePolicy": _fleet_twin_scope_policy(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }



# Phase 7.3 — Fleet State Change Intelligence
#
# Snapshot and selected-current comparisons describe operational workflow and
# evidence-state changes. They do not establish physical deterioration,
# physical improvement, causal maintenance effect, or reliability change.


def _fleet_change_scope_policy() -> dict:
    return {
        "selectedRunOnly": True,
        "defaultRunSelection": "latest_persisted_trained_run",
        "activeTelemetryExperimentRequired": False,
        "exactExperimentOnly": True,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "physicalConditionChange": False,
        "physicalRiskChange": False,
        "causalMaintenanceEffect": False,
        "reliabilityChangeProof": False,
        "modelRetrained": False,
        "benchmarkModified": False,
        "comparisonWrites": False,
    }


def _selected_fleet_snapshot(
    db: Session,
    *,
    run: DiagnosticModelRun,
    experiment_id: str,
    snapshot_id: int,
) -> DiagnosticFleetDecisionSnapshot:
    row = db.execute(
        select(DiagnosticFleetDecisionSnapshot)
        .where(
            DiagnosticFleetDecisionSnapshot.id == snapshot_id,
            DiagnosticFleetDecisionSnapshot.run_id == run.id,
            DiagnosticFleetDecisionSnapshot.experiment_id
            == experiment_id,
        )
        .limit(1)
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Fleet snapshot {snapshot_id} was not found in "
                f"selected diagnostic run {run.id}"
            ),
        )

    return row


def _fleet_change_inputs(
    db: Session,
    *,
    snapshot_from: int,
    snapshot_to: int | None,
    to_current: bool,
    run_id: int | None,
) -> tuple[
    str,
    DiagnosticModelRun,
    DiagnosticFleetDecisionSnapshot,
    DiagnosticFleetDecisionSnapshot | None,
    list[dict],
    list[dict],
]:
    if snapshot_to is not None and to_current:
        raise HTTPException(
            status_code=422,
            detail=(
                "Choose either snapshot_to or to_current=true, not both"
            ),
        )

    if snapshot_to is None and not to_current:
        raise HTTPException(
            status_code=422,
            detail=(
                "Provide snapshot_to or set to_current=true"
            ),
        )

    experiment_id, run = _resolve_vehicle_twin_run(
        db,
        run_id,
    )

    from_snapshot = _selected_fleet_snapshot(
        db,
        run=run,
        experiment_id=experiment_id,
        snapshot_id=snapshot_from,
    )

    before_records = _json_list(
        from_snapshot.records_json
    )

    to_snapshot = None

    if snapshot_to is not None:
        to_snapshot = _selected_fleet_snapshot(
            db,
            run=run,
            experiment_id=experiment_id,
            snapshot_id=snapshot_to,
        )

        after_records = _json_list(
            to_snapshot.records_json
        )
    else:
        (
            current_experiment_id,
            current_run,
            after_records,
        ) = _current_fleet_decision_records(
            db,
            selected_run=run,
        )

        if (
            current_run.id != run.id
            or current_experiment_id != experiment_id
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Selected current fleet state is not aligned "
                    "to the requested run"
                ),
            )

    return (
        experiment_id,
        run,
        from_snapshot,
        to_snapshot,
        before_records,
        after_records,
    )


@router.get("/fleet-change/snapshots")
def fleet_change_snapshots(
    limit: int = Query(default=50, ge=1, le=100),
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = _resolve_vehicle_twin_run(
        db,
        run_id,
    )

    total = int(
        db.scalar(
            select(
                func.count(
                    DiagnosticFleetDecisionSnapshot.id
                )
            ).where(
                DiagnosticFleetDecisionSnapshot.run_id == run.id,
                DiagnosticFleetDecisionSnapshot.experiment_id
                == experiment_id,
            )
        )
        or 0
    )

    rows = db.execute(
        select(DiagnosticFleetDecisionSnapshot)
        .where(
            DiagnosticFleetDecisionSnapshot.run_id == run.id,
            DiagnosticFleetDecisionSnapshot.experiment_id
            == experiment_id,
        )
        .order_by(
            desc(DiagnosticFleetDecisionSnapshot.created_at),
            desc(DiagnosticFleetDecisionSnapshot.id),
        )
        .limit(limit)
    ).scalars().all()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": FLEET_CHANGE_RULES_VERSION,
        "total": total,
        "returned": len(rows),
        "snapshots": [
            _fleet_decision_snapshot_payload(row)
            for row in rows
        ],
        "scopePolicy": _fleet_change_scope_policy(),
    }


@router.get("/fleet-change/compare")
def fleet_change_compare(
    snapshot_from: int = Query(ge=1),
    snapshot_to: int | None = Query(default=None, ge=1),
    to_current: bool = Query(default=False),
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    (
        experiment_id,
        run,
        from_snapshot,
        to_snapshot,
        before_records,
        after_records,
    ) = _fleet_change_inputs(
        db,
        snapshot_from=snapshot_from,
        snapshot_to=snapshot_to,
        to_current=to_current,
        run_id=run_id,
    )

    comparison = compare_fleet_states(
        before_records,
        after_records,
    )

    vehicle_changes = comparison.pop(
        "vehicleChanges"
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": FLEET_CHANGE_RULES_VERSION,
        "fromSnapshot": _fleet_decision_snapshot_payload(
            from_snapshot
        ),
        "toSnapshot": (
            _fleet_decision_snapshot_payload(to_snapshot)
            if to_snapshot is not None
            else None
        ),
        "toCurrent": to_snapshot is None,
        **comparison,
        "changedVehicleCount": sum(
            1
            for row in vehicle_changes
            if row["changed"]
        ),
        "scopePolicy": _fleet_change_scope_policy(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/fleet-change/vehicles")
def fleet_change_vehicles(
    snapshot_from: int = Query(ge=1),
    snapshot_to: int | None = Query(default=None, ge=1),
    to_current: bool = Query(default=False),
    transition: str | None = Query(default=None),
    changed_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    if (
        transition is not None
        and transition not in FLEET_CHANGE_TRANSITIONS
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unsupported fleet transition",
                "allowed": list(FLEET_CHANGE_TRANSITIONS),
            },
        )

    (
        experiment_id,
        run,
        from_snapshot,
        to_snapshot,
        before_records,
        after_records,
    ) = _fleet_change_inputs(
        db,
        snapshot_from=snapshot_from,
        snapshot_to=snapshot_to,
        to_current=to_current,
        run_id=run_id,
    )

    comparison = compare_fleet_states(
        before_records,
        after_records,
    )

    rows = comparison["vehicleChanges"]

    if changed_only:
        rows = [
            row
            for row in rows
            if row["changed"]
        ]

    if transition is not None:
        rows = [
            row
            for row in rows
            if transition in row["transitions"]
        ]

    rows.sort(
        key=lambda row: (
            abs(
                float(
                    row.get(
                        "attentionScoreDelta"
                    )
                    or 0.0
                )
            ),
            abs(
                float(
                    row.get(
                        "workloadUnitsDelta"
                    )
                    or 0.0
                )
            ),
            str(row["vehicleId"]),
        ),
        reverse=True,
    )

    selected = rows[:limit]

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": FLEET_CHANGE_RULES_VERSION,
        "fromSnapshotId": from_snapshot.id,
        "toSnapshotId": (
            to_snapshot.id
            if to_snapshot is not None
            else None
        ),
        "toCurrent": to_snapshot is None,
        "transitionFilter": transition,
        "changedOnly": changed_only,
        "totalMatching": len(rows),
        "returned": len(selected),
        "vehicles": selected,
        "scopePolicy": _fleet_change_scope_policy(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }



# Phase 7.4 — Capacity & Maintenance Planning Simulator
#
# Synthetic workflow-capacity planning only. Capacity units are prioritization
# units, not technician hours, physical service duration, labor estimates,
# failure-risk reduction, or automatic maintenance execution.


class CapacityPlanningSimulationRequest(BaseModel):
    capacityUnits: float = Field(ge=0.0, le=100000.0)
    strategy: str = Field(default="BALANCED")
    maxVehicles: int | None = Field(
        default=None,
        ge=1,
        le=500,
    )
    allowedMaintenanceTiers: list[str] = Field(
        default_factory=list
    )
    allowedDecisionStates: list[str] = Field(
        default_factory=list
    )
    runId: int | None = Field(
        default=None,
        ge=1,
    )


def _capacity_planning_scope_policy() -> dict:
    return {
        "selectedRunOnly": True,
        "defaultRunSelection": "latest_persisted_trained_run",
        "activeTelemetryExperimentRequired": False,
        "exactExperimentOnly": True,
        "scoringContextBoundedToPredictionAnchor": True,
        "postRunTelemetryUsed": False,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "simulationWrites": False,
        "automaticExecution": False,
        "automaticScheduling": False,
        "technicianHours": False,
        "physicalServiceDuration": False,
        "physicalOutcomePrediction": False,
        "physicalRiskReduction": False,
        "causalMaintenanceEffect": False,
        "modelRetrained": False,
        "benchmarkModified": False,
    }


@router.get("/capacity-planning/strategies")
def capacity_planning_strategies() -> dict:
    return {
        "rulesVersion": CAPACITY_PLANNING_RULES_VERSION,
        "strategies": list(
            CAPACITY_PLANNING_STRATEGIES
        ),
        "scopePolicy": _capacity_planning_scope_policy(),
        "interpretationPolicy": (
            "Strategies order synthetic operational workload only. "
            "They do not rank physical failure probability or technician "
            "service duration."
        ),
    }


@router.post("/capacity-planning/simulate")
def capacity_planning_simulate(
    request: CapacityPlanningSimulationRequest,
    db: Session = Depends(db_session),
) -> dict:
    if request.strategy not in CAPACITY_PLANNING_STRATEGIES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported capacity planning strategy"
                ),
                "allowed": list(
                    CAPACITY_PLANNING_STRATEGIES
                ),
            },
        )

    unknown_states = sorted(
        set(request.allowedDecisionStates)
        - set(DECISION_STATES)
    )

    if unknown_states:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported decision states"
                ),
                "invalid": unknown_states,
                "allowed": list(DECISION_STATES),
            },
        )

    experiment_id, run, records = (
        _current_fleet_twin_records(
            db,
            run_id=request.runId,
        )
    )

    result = simulate_capacity_plan(
        records,
        capacity_units=request.capacityUnits,
        strategy=request.strategy,
        max_vehicles=request.maxVehicles,
        allowed_maintenance_tiers=(
            request.allowedMaintenanceTiers
            or None
        ),
        allowed_decision_states=(
            request.allowedDecisionStates
            or None
        ),
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        **result,
        "scopePolicy": _capacity_planning_scope_policy(),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }



# Phase 7.5 — Policy & Workflow Effectiveness
#
# Read-only analysis of deterministic policy/action lifecycle metadata.
# Current target observation does not establish causal policy effectiveness,
# physical repair success, failure prevention, reliability improvement, or
# physical risk reduction.


def _workflow_effectiveness_scope_policy() -> dict:
    return {
        "selectedRunOnly": True,
        "defaultRunSelection": "latest_persisted_trained_run",
        "activeTelemetryExperimentRequired": False,
        "exactExperimentOnly": True,
        "runFrozenPrognosticInputs": True,
        "usesCurrentWorkflowMetadata": True,
        "postRunTelemetryUsed": False,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "analysisWrites": False,
        "automaticExecution": False,
        "causalAttribution": False,
        "physicalMaintenanceEffectiveness": False,
        "failurePreventionClaim": False,
        "reliabilityImprovementClaim": False,
        "physicalRiskReduction": False,
        "modelRetrained": False,
        "benchmarkModified": False,
    }


def _workflow_effectiveness_inputs(
    db: Session,
    *,
    run_id: int | None,
) -> tuple[
    str,
    DiagnosticModelRun,
    list[DiagnosticAutomationPolicy],
    list[DiagnosticAutomationAction],
    list[dict],
    dict[str, dict],
    dict[str, int],
]:
    experiment_id, run = _resolve_vehicle_twin_run(
        db,
        run_id,
    )

    policies = _current_automation_policies(
        db,
        run_id=run.id,
        experiment_id=experiment_id,
    )

    actions = db.execute(
        select(DiagnosticAutomationAction)
        .where(
            DiagnosticAutomationAction.run_id == run.id,
            DiagnosticAutomationAction.experiment_id
            == experiment_id,
        )
        .order_by(
            DiagnosticAutomationAction.created_at,
            DiagnosticAutomationAction.id,
        )
    ).scalars().all()

    (
        prognostic_experiment_id,
        prognostic_run,
        prognostic_records,
    ) = _current_prognostic_records(
        db,
        selected_run=run,
    )

    if (
        prognostic_run.id != run.id
        or prognostic_experiment_id != experiment_id
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Prognostic workflow inputs are not aligned "
                "to the selected effectiveness run"
            ),
        )

    (
        fleet_experiment_id,
        fleet_run,
        fleet_records,
    ) = _current_fleet_twin_records(
        db,
        run_id=run.id,
    )

    if (
        fleet_run.id != run.id
        or fleet_experiment_id != experiment_id
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Current fleet workflow metadata is not aligned "
                "to the selected effectiveness run"
            ),
        )

    current_by_vehicle = {
        str(record["vehicleId"]): record
        for record in fleet_records
    }

    matches = _automation_matches(
        prognostic_records,
        policies,
        include_disabled=False,
    )

    current_matches_by_policy = {
        policy.policy_key: sum(
            1
            for item in matches
            if item["policy"]["key"] == policy.policy_key
        )
        for policy in policies
    }

    return (
        experiment_id,
        run,
        policies,
        actions,
        prognostic_records,
        current_by_vehicle,
        current_matches_by_policy,
    )


def _workflow_action_record(
    row: DiagnosticAutomationAction,
) -> dict:
    return {
        "actionId": row.id,
        "policyId": row.policy_id,
        "policyKey": row.policy_key,
        "vehicleId": row.vehicle_id,
        "caseId": row.case_id,
        "actionType": row.action_type,
        "severity": row.severity,
        "status": row.status,
        "createdAt": row.created_at,
        "approvedAt": row.approved_at,
        "rejectedAt": row.rejected_at,
        "executedAt": row.executed_at,
        "sourceSnapshot": _json_object(
            row.source_snapshot_json
        ),
    }


def _workflow_policy_summary(
    policy: DiagnosticAutomationPolicy,
    actions: list[DiagnosticAutomationAction],
    current_by_vehicle: dict[str, dict],
    current_matches_by_policy: dict[str, int],
) -> dict:
    policy_actions = [
        row
        for row in actions
        if row.policy_key == policy.policy_key
    ]

    action_records = [
        _workflow_action_record(row)
        for row in policy_actions
    ]

    summary = summarize_policy_effectiveness(
        policy_key=policy.policy_key,
        actions=action_records,
        current_by_vehicle=current_by_vehicle,
        current_match_count=current_matches_by_policy.get(
            policy.policy_key,
            0,
        ),
    )

    return {
        "policyId": policy.id,
        "policyKey": policy.policy_key,
        "policyName": policy.name,
        "enabled": bool(policy.enabled),
        "priority": int(policy.priority),
        "severity": policy.severity,
        "actionType": policy.action_type,
        "requiresApproval": bool(
            policy.requires_approval
        ),
        **{
            key: value
            for key, value in summary.items()
            if key != "policyKey"
        },
    }


@router.get("/workflow-effectiveness/summary")
def workflow_effectiveness_summary(
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    (
        experiment_id,
        run,
        policies,
        actions,
        _,
        current_by_vehicle,
        current_matches_by_policy,
    ) = _workflow_effectiveness_inputs(
        db,
        run_id=run_id,
    )

    policy_summaries = [
        _workflow_policy_summary(
            policy,
            actions,
            current_by_vehicle,
            current_matches_by_policy,
        )
        for policy in policies
    ]

    aggregate = summarize_workflow_effectiveness(
        policy_summaries
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            WORKFLOW_EFFECTIVENESS_RULES_VERSION
        ),
        "enabledPolicies": sum(
            1
            for policy in policies
            if policy.enabled
        ),
        **aggregate,
        "scopePolicy": (
            _workflow_effectiveness_scope_policy()
        ),
        "interpretationPolicy": (
            "Effectiveness describes deterministic policy/action workflow "
            "throughput and current target-state observation. It does not "
            "prove that automation caused a workflow state, repaired a "
            "component, prevented failure, improved reliability, or reduced "
            "physical risk."
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get("/workflow-effectiveness/policies")
def workflow_effectiveness_policies(
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    (
        experiment_id,
        run,
        policies,
        actions,
        _,
        current_by_vehicle,
        current_matches_by_policy,
    ) = _workflow_effectiveness_inputs(
        db,
        run_id=run_id,
    )

    rows = [
        _workflow_policy_summary(
            policy,
            actions,
            current_by_vehicle,
            current_matches_by_policy,
        )
        for policy in policies
    ]

    rows.sort(
        key=lambda row: (
            int(row.get("executed") or 0),
            int(row.get("materializedActions") or 0),
            int(row.get("priority") or 0),
            str(row.get("policyKey") or ""),
        ),
        reverse=True,
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            WORKFLOW_EFFECTIVENESS_RULES_VERSION
        ),
        "totalPolicies": len(rows),
        "policies": rows,
        "scopePolicy": (
            _workflow_effectiveness_scope_policy()
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get(
    "/workflow-effectiveness/policies/{policy_key}"
)
def workflow_effectiveness_policy_detail(
    policy_key: str,
    run_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(db_session),
) -> dict:
    (
        experiment_id,
        run,
        policies,
        actions,
        _,
        current_by_vehicle,
        current_matches_by_policy,
    ) = _workflow_effectiveness_inputs(
        db,
        run_id=run_id,
    )

    policy = next(
        (
            row
            for row in policies
            if row.policy_key == policy_key
        ),
        None,
    )

    if policy is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Automation policy {policy_key!r} "
                f"was not found in selected run {run.id}"
            ),
        )

    policy_actions = [
        row
        for row in actions
        if row.policy_key == policy.policy_key
    ]

    action_records = [
        _workflow_action_record(row)
        for row in policy_actions
    ]

    summary = _workflow_policy_summary(
        policy,
        actions,
        current_by_vehicle,
        current_matches_by_policy,
    )

    action_rows = policy_action_effectiveness_rows(
        action_records,
        current_by_vehicle,
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            WORKFLOW_EFFECTIVENESS_RULES_VERSION
        ),
        "policy": summary,
        "actions": action_rows,
        "scopePolicy": (
            _workflow_effectiveness_scope_policy()
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get("/summary")
def diagnostics_summary(
    high_confidence_threshold: float = Query(default=0.70, ge=0.0, le=1.0),
    db: Session = Depends(db_session),
) -> dict:
    """Summarize current operational hypotheses for the active diagnostic run."""

    experiment_id, run = _require_current_run(db)

    class_rows = db.execute(
        select(
            DiagnosticPrediction.top_class,
            func.count(DiagnosticPrediction.id),
            func.avg(DiagnosticPrediction.top_confidence),
            func.max(DiagnosticPrediction.top_confidence),
        )
        .where(DiagnosticPrediction.run_id == run.id)
        .group_by(DiagnosticPrediction.top_class)
        .order_by(desc(func.count(DiagnosticPrediction.id)))
    ).all()

    total_vehicles = int(
        db.scalar(
            select(func.count(DiagnosticPrediction.id)).where(
                DiagnosticPrediction.run_id == run.id
            )
        )
        or 0
    )
    non_healthy_vehicles = int(
        db.scalar(
            select(func.count(DiagnosticPrediction.id)).where(
                DiagnosticPrediction.run_id == run.id,
                DiagnosticPrediction.top_class != "healthy",
            )
        )
        or 0
    )
    high_confidence_incidents = int(
        db.scalar(
            select(func.count(DiagnosticPrediction.id)).where(
                DiagnosticPrediction.run_id == run.id,
                DiagnosticPrediction.top_class != "healthy",
                DiagnosticPrediction.top_confidence >= high_confidence_threshold,
            )
        )
        or 0
    )
    average_confidence = db.scalar(
        select(func.avg(DiagnosticPrediction.top_confidence)).where(
            DiagnosticPrediction.run_id == run.id
        )
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "champion": run.champion,
        "totalVehicles": total_vehicles,
        "nonHealthyVehicles": non_healthy_vehicles,
        "highConfidenceIncidents": high_confidence_incidents,
        "highConfidenceThreshold": high_confidence_threshold,
        "averageTopConfidence": (
            round(float(average_confidence), 6)
            if average_confidence is not None
            else None
        ),
        "byClass": [
            {
                "class": top_class,
                "vehicles": int(vehicle_count),
                "averageConfidence": round(float(avg_confidence or 0.0), 6),
                "maxConfidence": round(float(max_confidence or 0.0), 6),
            }
            for top_class, vehicle_count, avg_confidence, max_confidence
            in class_rows
        ],
        "interpretationPolicy": (
            "Counts summarize current model hypotheses for the active "
            "diagnostic run; they are not failure ground truth."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }



# Phase 7.6 — Evidence & Explainability Center
#
# This layer explains FleetMind's own deterministic operational scoring and
# persisted evidence/workflow lineage. It is not SHAP, model feature
# attribution, causal attribution, physical failure truth, a physical
# dependency graph, calibrated risk, or physical RUL.


def _explainability_scope_policy() -> dict:
    return {
        "selectedRunOnly": True,
        "defaultRunSelection": (
            "latest_persisted_trained_run"
        ),
        "activeTelemetryExperimentRequired": False,
        "exactExperimentOnly": True,
        "scoringContextBoundedToPredictionAnchor": True,
        "postRunTelemetryUsed": False,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "shapValues": False,
        "modelFeatureAttribution": False,
        "causalAttribution": False,
        "causalGraph": False,
        "physicalRiskScore": False,
        "physicalFailureProbability": False,
        "physicalConditionProof": False,
        "physicalRul": False,
        "modelRetrained": False,
        "benchmarkModified": False,
        "writes": False,
    }


def _explainability_attention_record_from_twin(
    twin: dict,
) -> dict:
    """Project a Vehicle Twin into canonical Phase 7.0 score inputs."""

    model = twin.get("modelState") or {}
    diagnostic = twin.get("diagnosticState") or {}
    case = twin.get("caseState") or {}
    prognostic = twin.get("prognosticState") or {}
    maintenance = twin.get("maintenanceState") or {}
    automation = twin.get("automationState") or {}

    return {
        "topClass": model.get("topClass"),
        "topConfidence": model.get("topConfidence"),
        "episodeState": diagnostic.get(
            "episodeState"
        ),
        "caseId": case.get("caseId"),
        "caseStatus": case.get("status"),
        "reviewPriority": case.get(
            "reviewPriority"
        ),
        "assignedTo": case.get("assignedTo"),
        "watchlisted": bool(
            case.get("watchlisted")
        ),
        "maintenanceTier": prognostic.get(
            "maintenanceTier"
        ),
        "trajectoryEligible": prognostic.get(
            "trajectoryEligible"
        ),
        "maintenancePlanState": maintenance.get(
            "state"
        ),
        "automationStatuses": list(
            automation.get("statuses") or []
        ),
        "pendingActionTypes": list(
            automation.get(
                "pendingActionTypes"
            )
            or []
        ),
    }


def _explainability_vehicle_payload(
    twin: dict,
) -> dict:
    attention = attention_score_decomposition(
        _explainability_attention_record_from_twin(
            twin
        )
    )

    return {
        "vehicleId": twin.get("vehicleId"),
        "attention": attention,
        "evidenceInventory": evidence_inventory(
            twin
        ),
        "lineage": evidence_lineage(twin),
        "observableModelEvidence": list(
            (
                twin.get("modelState") or {}
            ).get("observableEvidence")
            or []
        ),
        "sourceVersions": dict(
            twin.get("sourceVersions") or {}
        ),
    }


@router.get("/explainability/summary")
def explainability_summary(
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = (
        _current_fleet_twin_records(
            db,
            run_id=run_id,
        )
    )

    summary = summarize_attention_explanations(
        records
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        **summary,
        "scopePolicy": (
            _explainability_scope_policy()
        ),
        "interpretationPolicy": (
            "Explains FleetMind's deterministic "
            "operational-attention scoring and "
            "evidence representation. Factors are "
            "not SHAP values, model feature "
            "attribution, causal evidence, physical "
            "failure probability, physical condition "
            "proof, or physical RUL."
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get("/explainability/vehicles")
def explainability_vehicles(
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    decision_state: str | None = Query(
        default=None,
    ),
    min_attention: float = Query(
        default=0.0,
        ge=0.0,
        le=100.0,
    ),
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    if (
        decision_state is not None
        and decision_state not in DECISION_STATES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported decision state"
                ),
                "allowed": list(
                    DECISION_STATES
                ),
            },
        )

    experiment_id, run, records = (
        _current_fleet_twin_records(
            db,
            run_id=run_id,
        )
    )

    rows = []

    for record in records:
        if (
            decision_state is not None
            and record.get("decisionState")
            != decision_state
        ):
            continue

        explanation = (
            attention_score_decomposition(
                record
            )
        )

        if (
            float(
                explanation.get(
                    "attentionScore"
                )
                or 0.0
            )
            < min_attention
        ):
            continue

        positive_components = [
            component
            for component
            in explanation["components"]
            if float(
                component.get(
                    "contribution"
                )
                or 0.0
            )
            > 0.0
        ]

        positive_components.sort(
            key=lambda component: (
                float(
                    component.get(
                        "contribution"
                    )
                    or 0.0
                ),
                str(
                    component.get(
                        "factor"
                    )
                    or ""
                ),
            ),
            reverse=True,
        )

        rows.append(
            {
                "vehicleId": record.get(
                    "vehicleId"
                ),
                "topClass": record.get(
                    "topClass"
                ),
                "topConfidence": record.get(
                    "topConfidence"
                ),
                "decisionState": record.get(
                    "decisionState"
                ),
                "attentionScore": (
                    explanation[
                        "attentionScore"
                    ]
                ),
                "rawAttentionScore": (
                    explanation[
                        "rawAttentionScore"
                    ]
                ),
                "capApplied": explanation[
                    "capApplied"
                ],
                "reconciles": explanation[
                    "reconciles"
                ],
                "coverageGaps": list(
                    explanation[
                        "coverageGaps"
                    ]
                ),
                "componentCount": len(
                    explanation["components"]
                ),
                "topFactors": (
                    positive_components[:3]
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            float(
                row.get(
                    "attentionScore"
                )
                or 0.0
            ),
            float(
                row.get(
                    "topConfidence"
                )
                or 0.0
            ),
            str(
                row.get("vehicleId")
                or ""
            ),
        ),
        reverse=True,
    )

    selected = rows[:limit]

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            EVIDENCE_EXPLAINABILITY_RULES_VERSION
        ),
        "totalMatched": len(rows),
        "returned": len(selected),
        "vehicles": selected,
        "scopePolicy": (
            _explainability_scope_policy()
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get(
    "/explainability/vehicles/{vehicle_id}"
)
def explainability_vehicle_detail(
    vehicle_id: str,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    _, selected_run = (
        _resolve_vehicle_twin_run(
            db,
            run_id,
        )
    )

    experiment_id, run, twin = (
        _current_vehicle_twin_record(
            db,
            vehicle_id,
            selected_run=selected_run,
        )
    )

    payload = _explainability_vehicle_payload(
        twin
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            EVIDENCE_EXPLAINABILITY_RULES_VERSION
        ),
        **payload,
        "scopePolicy": (
            _explainability_scope_policy()
        ),
        "interpretationPolicy": (
            "Unified selected-run operational "
            "explanation. Evidence presence and "
            "workflow lineage do not establish "
            "physical causality or component "
            "condition."
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get(
    "/explainability/vehicles/{vehicle_id}/attention"
)
def explainability_vehicle_attention(
    vehicle_id: str,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    _, selected_run = (
        _resolve_vehicle_twin_run(
            db,
            run_id,
        )
    )

    experiment_id, run, twin = (
        _current_vehicle_twin_record(
            db,
            vehicle_id,
            selected_run=selected_run,
        )
    )

    explanation = (
        attention_score_decomposition(
            _explainability_attention_record_from_twin(
                twin
            )
        )
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "vehicleId": vehicle_id,
        **explanation,
        "scopePolicy": (
            _explainability_scope_policy()
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get(
    "/explainability/vehicles/{vehicle_id}/lineage"
)
def explainability_vehicle_lineage(
    vehicle_id: str,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    _, selected_run = (
        _resolve_vehicle_twin_run(
            db,
            run_id,
        )
    )

    experiment_id, run, twin = (
        _current_vehicle_twin_record(
            db,
            vehicle_id,
            selected_run=selected_run,
        )
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "vehicleId": vehicle_id,
        "rulesVersion": (
            EVIDENCE_EXPLAINABILITY_RULES_VERSION
        ),
        "evidenceInventory": (
            evidence_inventory(twin)
        ),
        "evidenceLineage": (
            evidence_lineage(twin)
        ),
        "scopePolicy": (
            _explainability_scope_policy()
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }



# Phase 7.7 — Fleet Command Center
#
# The command center composes selected-run operational intelligence from
# existing FleetMind layers. Queue rank is workflow prioritization only.
# It is not calibrated physical risk, safety probability, component-condition
# proof, causal attribution, physical RUL, or technician-hour estimation.


FLEET_COMMAND_COHORT_DIMENSIONS = (
    "model",
    "factory",
    "firmware",
    "pumpRevision",
    "hypothesisClass",
)


def _fleet_command_scope_policy() -> dict:
    return {
        "selectedRunOnly": True,
        "defaultRunSelection": (
            "latest_persisted_trained_run"
        ),
        "activeTelemetryExperimentRequired": False,
        "exactExperimentOnly": True,
        "scoringContextBoundedToPredictionAnchor": True,
        "postRunTelemetryUsed": False,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "queuePriorityIsPhysicalRisk": False,
        "physicalFailureProbability": False,
        "physicalSafetyProbability": False,
        "physicalConditionProof": False,
        "physicalRul": False,
        "causalAttribution": False,
        "technicianHours": False,
        "modelRetrained": False,
        "benchmarkModified": False,
        "writes": False,
    }


def _fleet_command_workflow_rollup(
    db: Session,
    *,
    run_id: int,
) -> dict:
    """Reuse the canonical Phase 7.5 effectiveness endpoint logic."""

    payload = workflow_effectiveness_summary(
        run_id=run_id,
        db=db,
    )

    return {
        "rulesVersion": payload.get(
            "rulesVersion"
        ),
        "totalPolicies": payload.get(
            "totalPolicies"
        ),
        "totalActions": payload.get(
            "totalActions"
        ),
        "pendingApproval": payload.get(
            "pendingApproval"
        ),
        "approvedReady": payload.get(
            "approvedReady"
        ),
        "rejected": payload.get(
            "rejected"
        ),
        "executed": payload.get(
            "executed"
        ),
        "everApproved": payload.get(
            "everApproved"
        ),
        "currentMatches": payload.get(
            "currentMatches"
        ),
    }


@router.get("/fleet-command/summary")
def fleet_command_summary(
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = (
        _current_fleet_twin_records(
            db,
            run_id=run_id,
        )
    )

    command = command_center_summary(
        records
    )

    explanation = (
        summarize_attention_explanations(
            records
        )
    )

    workflow = (
        _fleet_command_workflow_rollup(
            db,
            run_id=run.id,
        )
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        **command,
        "workflow": workflow,
        "attentionExplanation": {
            "rulesVersion": explanation.get(
                "rulesVersion"
            ),
            "reconciledVehicleCount": (
                explanation.get(
                    "reconciledVehicleCount"
                )
            ),
            "cappedVehicleCount": (
                explanation.get(
                    "cappedVehicleCount"
                )
            ),
            "topFactors": list(
                explanation.get("factors")
                or []
            )[:10],
        },
        "scopePolicy": (
            _fleet_command_scope_policy()
        ),
        "interpretationPolicy": (
            "Fleet Command composes selected-run "
            "operational state. Command queues and "
            "attention ordering describe workflow "
            "priority only, not physical failure "
            "risk, safety probability, component "
            "condition, causality, or physical RUL."
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get("/fleet-command/queues")
def fleet_command_queues(
    queue: str | None = Query(
        default=None,
    ),
    limit: int = Query(
        default=25,
        ge=1,
        le=500,
    ),
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    if (
        queue is not None
        and queue not in FLEET_COMMAND_QUEUES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported Fleet Command queue"
                ),
                "allowed": list(
                    FLEET_COMMAND_QUEUES
                ),
            },
        )

    experiment_id, run, records = (
        _current_fleet_twin_records(
            db,
            run_id=run_id,
        )
    )

    if queue is not None:
        rows = command_queue_rows(
            records,
            queue,
        )

        return {
            "runId": run.id,
            "experimentId": experiment_id,
            "lineage": run.lineage,
            "rulesVersion": (
                FLEET_COMMAND_RULES_VERSION
            ),
            "queue": queue,
            "totalMatched": len(rows),
            "returned": min(
                len(rows),
                limit,
            ),
            "vehicles": rows[:limit],
            "scopePolicy": (
                _fleet_command_scope_policy()
            ),
            "generatedAt": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    queue_payloads = []

    for queue_name in FLEET_COMMAND_QUEUES:
        rows = command_queue_rows(
            records,
            queue_name,
        )

        queue_payloads.append(
            {
                "queue": queue_name,
                "vehicles": len(rows),
                "topVehicles": rows[
                    : min(limit, len(rows))
                ],
            }
        )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            FLEET_COMMAND_RULES_VERSION
        ),
        "queueCount": len(
            FLEET_COMMAND_QUEUES
        ),
        "queues": queue_payloads,
        "scopePolicy": (
            _fleet_command_scope_policy()
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get("/fleet-command/vehicles")
def fleet_command_vehicles(
    queue: str | None = Query(
        default=None,
    ),
    decision_state: str | None = Query(
        default=None,
    ),
    min_attention: float = Query(
        default=0.0,
        ge=0.0,
        le=100.0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    if (
        queue is not None
        and queue not in FLEET_COMMAND_QUEUES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported Fleet Command queue"
                ),
                "allowed": list(
                    FLEET_COMMAND_QUEUES
                ),
            },
        )

    if (
        decision_state is not None
        and decision_state not in DECISION_STATES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported decision state"
                ),
                "allowed": list(
                    DECISION_STATES
                ),
            },
        )

    experiment_id, run, records = (
        _current_fleet_twin_records(
            db,
            run_id=run_id,
        )
    )

    selected_records = []

    for record in records:
        if (
            queue is not None
            and not queue_match(
                record,
                queue,
            )
        ):
            continue

        if (
            decision_state is not None
            and record.get(
                "decisionState"
            )
            != decision_state
        ):
            continue

        if (
            float(
                record.get(
                    "attentionScore"
                )
                or 0.0
            )
            < min_attention
        ):
            continue

        selected_records.append(
            record
        )

    rows = command_vehicle_rows(
        selected_records
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            FLEET_COMMAND_RULES_VERSION
        ),
        "totalMatched": len(rows),
        "returned": min(
            len(rows),
            limit,
        ),
        "vehicles": rows[:limit],
        "scopePolicy": (
            _fleet_command_scope_policy()
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get("/fleet-command/cohorts")
def fleet_command_cohorts(
    dimension: str = Query(
        default="factory",
    ),
    measure: str = Query(
        default="nonHealthy",
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
    ),
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    if (
        dimension
        not in FLEET_COMMAND_COHORT_DIMENSIONS
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported Fleet Command "
                    "cohort dimension"
                ),
                "allowed": list(
                    FLEET_COMMAND_COHORT_DIMENSIONS
                ),
            },
        )

    if (
        measure
        not in FLEET_TWIN_EXPOSURE_MEASURES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported Fleet Command "
                    "exposure measure"
                ),
                "allowed": list(
                    FLEET_TWIN_EXPOSURE_MEASURES
                ),
            },
        )

    experiment_id, run, records = (
        _current_fleet_twin_records(
            db,
            run_id=run_id,
        )
    )

    rows = cohort_exposure_rows(
        records,
        dimension,
    )

    rows.sort(
        key=lambda row: (
            exposure_measure_rate(
                row,
                measure,
            ),
            int(
                row.get(
                    "populationCount"
                )
                or 0
            ),
            str(
                row.get("value")
                or ""
            ),
        ),
        reverse=True,
    )

    selected = rows[:limit]

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            FLEET_COMMAND_RULES_VERSION
        ),
        "sourceExposureRulesVersion": (
            FLEET_TWIN_RULES_VERSION
        ),
        "dimension": dimension,
        "measure": measure,
        "fleetBaseline": (
            fleet_exposure_summary(
                records
            )
        ),
        "totalCohorts": len(rows),
        "returnedCohorts": len(
            selected
        ),
        "cohorts": selected,
        "scopePolicy": (
            _fleet_command_scope_policy()
        ),
        "interpretationPolicy": (
            "Cohort watch uses normalized Phase "
            "7.2 operational representation rates. "
            "Higher representation is not greater "
            "physical failure risk, lower reliability, "
            "causality, or component-condition proof."
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }



# Phase 8.0 — Closed-Loop Operations Foundation
#
# Recommendations are persisted workflow metadata. Their lifecycle execution
# means the FleetMind recommendation record completed its explicitly approved
# workflow. It does not mean physical maintenance, component replacement,
# vehicle actuation, repair success, failure prevention, or safety clearance.


class ClosedLoopEvaluateRequest(BaseModel):
    actor: str = Field(
        min_length=1,
        max_length=64,
    )
    materialize: bool = False
    vehicleIds: list[str] | None = None


class ClosedLoopTransitionRequest(BaseModel):
    actor: str = Field(
        min_length=1,
        max_length=64,
    )
    note: str | None = Field(
        default=None,
        max_length=2000,
    )


def _closed_loop_scope_policy() -> dict:
    return {
        "selectedRunOnly": True,
        "activeTelemetryExperimentRequired": False,
        "exactExperimentOnly": True,
        "scoringContextBoundedToPredictionAnchor": True,
        "postRunTelemetryUsed": False,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "recommendationMetadataOnly": True,
        "automaticApproval": False,
        "automaticExecution": False,
        "physicalAction": False,
        "physicalMaintenanceCommand": False,
        "vehicleActuation": False,
        "physicalRepairConfirmation": False,
        "physicalFailurePreventionClaim": False,
        "causalAttribution": False,
        "modelRetrained": False,
        "benchmarkModified": False,
    }


def _closed_loop_source_snapshot(
    record: dict,
    candidate: dict,
) -> dict:
    """Persist bounded operational evidence used to create a recommendation."""

    return {
        "vehicleId": record.get(
            "vehicleId"
        ),
        "caseId": record.get(
            "caseId"
        ),
        "topClass": record.get(
            "topClass"
        ),
        "topConfidence": record.get(
            "topConfidence"
        ),
        "episodeState": record.get(
            "episodeState"
        ),
        "caseStatus": record.get(
            "caseStatus"
        ),
        "reviewPriority": record.get(
            "reviewPriority"
        ),
        "assignedTo": record.get(
            "assignedTo"
        ),
        "maintenanceTier": record.get(
            "maintenanceTier"
        ),
        "trajectoryEligible": record.get(
            "trajectoryEligible"
        ),
        "decisionState": record.get(
            "decisionState"
        ),
        "attentionScore": record.get(
            "attentionScore"
        ),
        "workloadUnits": record.get(
            "workloadUnits"
        ),
        "coverageGaps": list(
            record.get("coverageGaps")
            or []
        ),
        "automationStatus": record.get(
            "automationStatus"
        ),
        "automationStatuses": list(
            record.get(
                "automationStatuses"
            )
            or []
        ),
        "pendingActionTypes": list(
            record.get(
                "pendingActionTypes"
            )
            or []
        ),
        "scoringContextTimestamp": record.get(
            "scoringContextTimestamp"
        ),
        "scoringContextMileage": record.get(
            "scoringContextMileage"
        ),
        "recommendation": {
            "recommendationType": (
                candidate[
                    "recommendationType"
                ]
            ),
            "priority": candidate[
                "priority"
            ],
            "reason": candidate[
                "reason"
            ],
            "sourceKey": candidate[
                "sourceKey"
            ],
        },
    }


def _closed_loop_recommendation_payload(
    row: DiagnosticOperationalRecommendation,
) -> dict:
    return {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "vehicleId": row.vehicle_id,
        "caseId": row.case_id,
        "recommendationKey": (
            row.recommendation_key
        ),
        "rulesVersion": row.rules_version,
        "recommendationType": (
            row.recommendation_type
        ),
        "priority": row.priority,
        "status": row.status,
        "approvalRequired": (
            bool(row.approval_required)
        ),
        "sourceKey": row.source_key,
        "reason": row.reason,
        "sourceSnapshot": _json_object(
            row.source_snapshot_json
        ),
        "createdAt": (
            row.created_at.isoformat()
        ),
        "updatedAt": (
            row.updated_at.isoformat()
        ),
        "materializedBy": (
            row.materialized_by
        ),
        "lastActor": row.last_actor,
        "assignedTo": row.assigned_to,
        "assignedAt": (
            row.assigned_at.isoformat() if row.assigned_at else None
        ),
        "acknowledgedAt": (
            row.acknowledged_at.isoformat()
            if row.acknowledged_at
            else None
        ),
        "approvalRequiredAt": (
            row.approval_required_at.isoformat()
            if row.approval_required_at
            else None
        ),
        "approvedAt": (
            row.approved_at.isoformat()
            if row.approved_at
            else None
        ),
        "executionReadyAt": (
            row.execution_ready_at.isoformat()
            if row.execution_ready_at
            else None
        ),
        "executedAt": (
            row.executed_at.isoformat()
            if row.executed_at
            else None
        ),
        "rejectedAt": (
            row.rejected_at.isoformat()
            if row.rejected_at
            else None
        ),
        "cancelledAt": (
            row.cancelled_at.isoformat()
            if row.cancelled_at
            else None
        ),
        "supersededAt": (
            row.superseded_at.isoformat()
            if row.superseded_at
            else None
        ),
    }


def _closed_loop_activity_payload(
    row: DiagnosticOperationalRecommendationActivity,
) -> dict:
    return {
        "id": row.id,
        "recommendationId": (
            row.recommendation_id
        ),
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "vehicleId": row.vehicle_id,
        "createdAt": (
            row.created_at.isoformat()
        ),
        "activityType": (
            row.activity_type
        ),
        "actor": row.actor,
        "fromState": row.from_state,
        "toState": row.to_state,
        "note": row.note_text,
        "details": _json_object(
            row.details_json
        ),
    }


def _closed_loop_add_activity(
    db: Session,
    *,
    recommendation: DiagnosticOperationalRecommendation,
    activity_type: str,
    actor: str,
    from_state: str | None,
    to_state: str | None,
    note: str | None = None,
    details: dict | None = None,
    created_at: datetime | None = None,
) -> DiagnosticOperationalRecommendationActivity:
    row = DiagnosticOperationalRecommendationActivity(
        recommendation_id=(
            recommendation.id
        ),
        run_id=recommendation.run_id,
        experiment_id=(
            recommendation.experiment_id
        ),
        vehicle_id=(
            recommendation.vehicle_id
        ),
        created_at=(
            created_at
            or datetime.now(
                timezone.utc
            )
        ),
        activity_type=activity_type,
        actor=actor,
        from_state=from_state,
        to_state=to_state,
        note_text=note,
        details_json=json.dumps(
            details or {},
            sort_keys=True,
        ),
    )

    db.add(row)

    return row


def _closed_loop_set_state_timestamp(
    row: DiagnosticOperationalRecommendation,
    state: str,
    timestamp: datetime,
) -> None:
    if state == STATE_ACKNOWLEDGED:
        row.acknowledged_at = timestamp

    elif state == STATE_APPROVAL_REQUIRED:
        row.approval_required_at = timestamp

    elif state == STATE_APPROVED:
        row.approved_at = timestamp

    elif state == STATE_EXECUTION_READY:
        row.execution_ready_at = timestamp

    elif state == STATE_EXECUTED:
        row.executed_at = timestamp

    elif state == STATE_REJECTED:
        row.rejected_at = timestamp

    elif state == STATE_CANCELLED:
        row.cancelled_at = timestamp

    elif state == STATE_SUPERSEDED:
        row.superseded_at = timestamp


def _closed_loop_selected_recommendation(
    db: Session,
    *,
    recommendation_id: int,
    run_id: int | None,
) -> tuple[
    str,
    DiagnosticModelRun,
    DiagnosticOperationalRecommendation,
]:
    experiment_id, run = (
        _resolve_vehicle_twin_run(
            db,
            run_id,
        )
    )

    row = db.execute(
        select(
            DiagnosticOperationalRecommendation
        )
        .where(
            DiagnosticOperationalRecommendation.id
            == recommendation_id,
            DiagnosticOperationalRecommendation.run_id
            == run.id,
            DiagnosticOperationalRecommendation.experiment_id
            == experiment_id,
        )
        .limit(1)
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Closed-loop recommendation "
                f"{recommendation_id} was not "
                "found for the selected run."
            ),
        )

    return experiment_id, run, row


def _closed_loop_transition(
    db: Session,
    *,
    recommendation: DiagnosticOperationalRecommendation,
    target_state: str,
    activity_type: str,
    actor: str,
    note: str | None,
) -> bool:
    """Perform exactly one permitted lifecycle transition."""

    current_state = recommendation.status

    if current_state == target_state:
        return False

    try:
        require_transition(
            current_state,
            target_state,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    now = datetime.now(
        timezone.utc
    )

    recommendation.status = (
        target_state
    )
    recommendation.updated_at = now
    recommendation.last_actor = actor

    _closed_loop_set_state_timestamp(
        recommendation,
        target_state,
        now,
    )

    _closed_loop_add_activity(
        db,
        recommendation=recommendation,
        activity_type=activity_type,
        actor=actor,
        from_state=current_state,
        to_state=target_state,
        note=note,
        created_at=now,
        details={
            "workflowMetadataOnly": True,
            "physicalAction": False,
        },
    )

    db.commit()
    db.refresh(recommendation)

    return True


@router.post(
    "/closed-loop/recommendations/evaluate"
)
def closed_loop_evaluate(
    request: ClosedLoopEvaluateRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, records = (
        _current_fleet_twin_records(
            db,
            run_id=run_id,
        )
    )

    if request.vehicleIds:
        requested_ids = {
            value.strip()
            for value
            in request.vehicleIds
            if value.strip()
        }

        records = [
            record
            for record in records
            if str(
                record.get(
                    "vehicleId"
                )
            )
            in requested_ids
        ]

    summary = (
        summarize_recommendation_candidates(
            records
        )
    )

    prepared = []

    for record in records:
        for candidate in (
            recommendation_candidates(
                record
            )
        ):
            key = recommendation_key(
                run_id=run.id,
                experiment_id=(
                    experiment_id
                ),
                vehicle_id=str(
                    record[
                        "vehicleId"
                    ]
                ),
                recommendation_type=(
                    candidate[
                        "recommendationType"
                    ]
                ),
                case_id=(
                    candidate.get(
                        "caseId"
                    )
                ),
                source_key=(
                    candidate.get(
                        "sourceKey"
                    )
                ),
            )

            prepared.append(
                {
                    "record": record,
                    "candidate": candidate,
                    "recommendationKey": key,
                }
            )

    preview = [
        {
            **item["candidate"],
            "recommendationKey": (
                item[
                    "recommendationKey"
                ]
            ),
        }
        for item in prepared
    ]

    if not request.materialize:
        return {
            "runId": run.id,
            "experimentId": experiment_id,
            "lineage": run.lineage,
            "rulesVersion": (
                CLOSED_LOOP_RULES_VERSION
            ),
            **summary,
            "materializeRequested": False,
            "createdCount": 0,
            "existingCount": 0,
            "candidates": preview,
            "scopePolicy": (
                _closed_loop_scope_policy()
            ),
            "generatedAt": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    keys = [
        item[
            "recommendationKey"
        ]
        for item in prepared
    ]

    existing_by_key = {}

    if keys:
        existing_rows = db.execute(
            select(
                DiagnosticOperationalRecommendation
            ).where(
                DiagnosticOperationalRecommendation.recommendation_key.in_(
                    keys
                )
            )
        ).scalars().all()

        existing_by_key = {
            row.recommendation_key: row
            for row in existing_rows
        }

    created = []

    now = datetime.now(
        timezone.utc
    )

    for item in prepared:
        key = item[
            "recommendationKey"
        ]

        if key in existing_by_key:
            continue

        record = item["record"]
        candidate = item[
            "candidate"
        ]

        row = (
            DiagnosticOperationalRecommendation(
                run_id=run.id,
                experiment_id=(
                    experiment_id
                ),
                vehicle_id=str(
                    record[
                        "vehicleId"
                    ]
                ),
                case_id=(
                    candidate.get(
                        "caseId"
                    )
                ),
                recommendation_key=key,
                rules_version=(
                    CLOSED_LOOP_RULES_VERSION
                ),
                recommendation_type=(
                    candidate[
                        "recommendationType"
                    ]
                ),
                priority=(
                    candidate[
                        "priority"
                    ]
                ),
                status=STATE_PROPOSED,
                approval_required=True,
                source_key=str(
                    candidate[
                        "sourceKey"
                    ]
                ),
                reason=str(
                    candidate[
                        "reason"
                    ]
                ),
                source_snapshot_json=(
                    json.dumps(
                        _closed_loop_source_snapshot(
                            record,
                            candidate,
                        ),
                        sort_keys=True,
                    )
                ),
                created_at=now,
                updated_at=now,
                materialized_by=(
                    request.actor
                ),
                last_actor=(
                    request.actor
                ),
            )
        )

        # The recommendation key is database-unique. The initial bulk lookup
        # handles ordinary repeat requests; this savepoint also handles the
        # narrower race where another request inserts the same key after that
        # lookup but before this request flushes its insert.
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()

                _closed_loop_add_activity(
                    db,
                    recommendation=row,
                    activity_type="CREATED",
                    actor=request.actor,
                    from_state=None,
                    to_state=STATE_PROPOSED,
                    created_at=now,
                    details={
                        "materializedFromEvaluation": True,
                        "automaticApproval": False,
                        "automaticExecution": False,
                        "physicalAction": False,
                    },
                )

                # Keep recommendation + CREATED audit activity atomic inside
                # the same savepoint.
                db.flush()
        except IntegrityError:
            # A concurrent request may have won the unique-key race. Rollback
            # is scoped to the savepoint, so recommendations created earlier
            # in this request remain part of the outer transaction.
            existing = db.execute(
                select(
                    DiagnosticOperationalRecommendation
                ).where(
                    DiagnosticOperationalRecommendation.recommendation_key
                    == key
                )
            ).scalar_one_or_none()

            if existing is None:
                # The integrity failure was unrelated to recommendation-key
                # idempotency; preserve the real database error.
                raise

            existing_by_key[key] = existing
            continue

        # Also protects against a duplicate key appearing twice in the same
        # prepared candidate set before the final commit.
        existing_by_key[key] = row
        created.append(row)

    db.commit()

    for row in created:
        db.refresh(row)

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            CLOSED_LOOP_RULES_VERSION
        ),
        **summary,
        "materializeRequested": True,
        "createdCount": len(
            created
        ),
        "existingCount": (
            len(prepared)
            - len(created)
        ),
        "totalPersistedTargets": len(
            prepared
        ),
        "scopePolicy": (
            _closed_loop_scope_policy()
        ),
        "interpretationPolicy": (
            "Materialization creates recommendation "
            "workflow metadata only. No recommendation "
            "is approved or executed automatically and "
            "no diagnostic, maintenance, automation, "
            "vehicle, or physical state is changed."
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get(
    "/closed-loop/recommendations"
)
def closed_loop_recommendations(
    status: str | None = Query(
        default=None,
    ),
    recommendation_type: str | None = Query(
        default=None,
    ),
    priority: str | None = Query(
        default=None,
    ),
    vehicle_id: str | None = Query(
        default=None,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    if (
        status is not None
        and status
        not in CLOSED_LOOP_STATES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported recommendation status"
                ),
                "allowed": list(
                    CLOSED_LOOP_STATES
                ),
            },
        )

    if (
        recommendation_type is not None
        and recommendation_type
        not in CLOSED_LOOP_RECOMMENDATION_TYPES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported recommendation type"
                ),
                "allowed": list(
                    CLOSED_LOOP_RECOMMENDATION_TYPES
                ),
            },
        )

    if (
        priority is not None
        and priority
        not in CLOSED_LOOP_PRIORITIES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported recommendation priority"
                ),
                "allowed": list(
                    CLOSED_LOOP_PRIORITIES
                ),
            },
        )

    experiment_id, run = (
        _resolve_vehicle_twin_run(
            db,
            run_id,
        )
    )

    statement = select(
        DiagnosticOperationalRecommendation
    ).where(
        DiagnosticOperationalRecommendation.run_id
        == run.id,
        DiagnosticOperationalRecommendation.experiment_id
        == experiment_id,
    )

    if status is not None:
        statement = statement.where(
            DiagnosticOperationalRecommendation.status
            == status
        )

    if recommendation_type is not None:
        statement = statement.where(
            DiagnosticOperationalRecommendation.recommendation_type
            == recommendation_type
        )

    if priority is not None:
        statement = statement.where(
            DiagnosticOperationalRecommendation.priority
            == priority
        )

    if vehicle_id is not None:
        statement = statement.where(
            DiagnosticOperationalRecommendation.vehicle_id
            == vehicle_id
        )

    rows = db.execute(
        statement.order_by(
            DiagnosticOperationalRecommendation.created_at,
            DiagnosticOperationalRecommendation.id,
        )
    ).scalars().all()

    selected = rows[:limit]

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            CLOSED_LOOP_RULES_VERSION
        ),
        "totalMatched": len(rows),
        "returned": len(selected),
        "recommendations": [
            _closed_loop_recommendation_payload(
                row
            )
            for row in selected
        ],
        "scopePolicy": (
            _closed_loop_scope_policy()
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.get(
    "/closed-loop/recommendations/{recommendation_id}"
)
def closed_loop_recommendation_detail(
    recommendation_id: int,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, row = (
        _closed_loop_selected_recommendation(
            db,
            recommendation_id=(
                recommendation_id
            ),
            run_id=run_id,
        )
    )

    activities = db.execute(
        select(
            DiagnosticOperationalRecommendationActivity
        )
        .where(
            DiagnosticOperationalRecommendationActivity.recommendation_id
            == row.id,
            DiagnosticOperationalRecommendationActivity.run_id
            == run.id,
            DiagnosticOperationalRecommendationActivity.experiment_id
            == experiment_id,
        )
        .order_by(
            DiagnosticOperationalRecommendationActivity.created_at,
            DiagnosticOperationalRecommendationActivity.id,
        )
    ).scalars().all()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            CLOSED_LOOP_RULES_VERSION
        ),
        "recommendation": (
            _closed_loop_recommendation_payload(
                row
            )
        ),
        "activities": [
            _closed_loop_activity_payload(
                activity
            )
            for activity in activities
        ],
        "scopePolicy": (
            _closed_loop_scope_policy()
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


def _closed_loop_transition_response(
    db: Session,
    *,
    recommendation_id: int,
    run_id: int | None,
    request: ClosedLoopTransitionRequest,
    target_state: str,
    activity_type: str,
) -> dict:
    experiment_id, run, row = (
        _closed_loop_selected_recommendation(
            db,
            recommendation_id=(
                recommendation_id
            ),
            run_id=run_id,
        )
    )

    changed = _closed_loop_transition(
        db,
        recommendation=row,
        target_state=target_state,
        activity_type=activity_type,
        actor=request.actor,
        note=request.note,
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": (
            CLOSED_LOOP_RULES_VERSION
        ),
        "changed": changed,
        "recommendation": (
            _closed_loop_recommendation_payload(
                row
            )
        ),
        "scopePolicy": (
            _closed_loop_scope_policy()
        ),
        "interpretationPolicy": (
            "This transition changes only the "
            "FleetMind recommendation lifecycle. "
            "It does not prove or perform physical "
            "maintenance or vehicle actuation."
        ),
    }


@router.post(
    "/closed-loop/recommendations/{recommendation_id}/acknowledge"
)
def closed_loop_acknowledge(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _closed_loop_transition_response(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_ACKNOWLEDGED,
        activity_type="ACKNOWLEDGED",
    )


@router.post(
    "/closed-loop/recommendations/{recommendation_id}/request-approval"
)
def closed_loop_request_approval(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _closed_loop_transition_response(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=(
            STATE_APPROVAL_REQUIRED
        ),
        activity_type=(
            "APPROVAL_REQUESTED"
        ),
    )


@router.post(
    "/closed-loop/recommendations/{recommendation_id}/approve"
)
def closed_loop_approve(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _closed_loop_transition_response(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_APPROVED,
        activity_type="APPROVED",
    )


@router.post(
    "/closed-loop/recommendations/{recommendation_id}/mark-execution-ready"
)
def closed_loop_mark_execution_ready(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _closed_loop_transition_response(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=(
            STATE_EXECUTION_READY
        ),
        activity_type="EXECUTION_READY",
    )


@router.post(
    "/closed-loop/recommendations/{recommendation_id}/execute"
)
def closed_loop_execute(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _closed_loop_transition_response(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_EXECUTED,
        activity_type="EXECUTED",
    )


@router.post(
    "/closed-loop/recommendations/{recommendation_id}/reject"
)
def closed_loop_reject(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _closed_loop_transition_response(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_REJECTED,
        activity_type="REJECTED",
    )


@router.post(
    "/closed-loop/recommendations/{recommendation_id}/cancel"
)
def closed_loop_cancel(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _closed_loop_transition_response(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_CANCELLED,
        activity_type="CANCELLED",
    )


@router.post(
    "/closed-loop/recommendations/{recommendation_id}/supersede"
)
def closed_loop_supersede(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _closed_loop_transition_response(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_SUPERSEDED,
        activity_type="SUPERSEDED",
    )



# Phase 8.1 — Decision Queue & Approval Orchestration
#
# Queue age, priority and review targets are internal workflow conventions.
# They are not physical safety deadlines, physical-risk estimates,
# technician-hour estimates, maintenance-duration promises, contractual
# service-level agreements, or evidence of component condition.


class DecisionQueueAssignmentRequest(BaseModel):
    actor: str = Field(
        min_length=1,
        max_length=64,
    )
    assignedTo: str | None = Field(
        default=None,
        max_length=64,
    )
    note: str | None = Field(
        default=None,
        max_length=2000,
    )


def _decision_queue_scope_policy() -> dict:
    return {
        "selectedRunOnly": True,
        "activeTelemetryExperimentRequired": False,
        "exactExperimentOnly": True,
        "postRunTelemetryUsed": False,
        "usesPrivateFailureTruth": False,
        "failureMarkersExposed": False,
        "workflowQueueOnly": True,
        "assignmentMetadataOnly": True,
        "automaticAssignment": False,
        "automaticApproval": False,
        "automaticExecution": False,
        "reviewTargetIsSafetyDeadline": False,
        "reviewTargetIsContractualSla": False,
        "priorityIsPhysicalRisk": False,
        "ageIsPhysicalCondition": False,
        "technicianHours": False,
        "physicalMaintenanceDuration": False,
        "physicalAction": False,
        "vehicleActuation": False,
        "causalAttribution": False,
        "modelRetrained": False,
        "benchmarkModified": False,
    }


def _decision_queue_input(
    row: DiagnosticOperationalRecommendation,
) -> dict:
    """Project persistence state into the pure Phase 8.1 queue rules."""

    return {
        "id": row.id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "vehicleId": row.vehicle_id,
        "caseId": row.case_id,
        "recommendationType": (
            row.recommendation_type
        ),
        "priority": row.priority,
        "status": row.status,
        "approvalRequired": (
            bool(row.approval_required)
        ),
        "assignedTo": row.assigned_to,
        "assignedAt": row.assigned_at,
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }


def _decision_queue_persisted_rows(
    db: Session,
    *,
    run: DiagnosticModelRun,
    experiment_id: str,
) -> list[
    DiagnosticOperationalRecommendation
]:
    return list(
        db.execute(
            select(
                DiagnosticOperationalRecommendation
            )
            .where(
                DiagnosticOperationalRecommendation.run_id
                == run.id,
                DiagnosticOperationalRecommendation.experiment_id
                == experiment_id,
            )
            .order_by(
                DiagnosticOperationalRecommendation.id
            )
        )
        .scalars()
        .all()
    )


def _decision_queue_counts(
    rows: list[
        DiagnosticOperationalRecommendation
    ],
) -> dict:
    return {
        "total": len(rows),
        "assigned": sum(
            1
            for row in rows
            if row.assigned_to
        ),
        "unassigned": sum(
            1
            for row in rows
            if not row.assigned_to
        ),
    }


@router.get("/decision-queue/summary")
def decision_queue_summary_api(
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run = (
        _resolve_vehicle_twin_run(
            db,
            run_id,
        )
    )

    persisted = (
        _decision_queue_persisted_rows(
            db,
            run=run,
            experiment_id=experiment_id,
        )
    )

    now = datetime.now(
        timezone.utc
    )

    summary = decision_queue_summary(
        [
            _decision_queue_input(row)
            for row in persisted
        ],
        now=now,
    )

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        **summary,
        "assignment": (
            _decision_queue_counts(
                persisted
            )
        ),
        "scopePolicy": (
            _decision_queue_scope_policy()
        ),
        "generatedAt": (
            now.isoformat()
        ),
    }


@router.get("/decision-queue")
def decision_queue_list(
    status: str | None = Query(
        default=None,
    ),
    priority: str | None = Query(
        default=None,
    ),
    recommendation_type: str | None = Query(
        default=None,
    ),
    assigned_to: str | None = Query(
        default=None,
    ),
    unassigned: bool | None = Query(
        default=None,
    ),
    include_terminal: bool = Query(
        default=False,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    if (
        status is not None
        and status not in CLOSED_LOOP_STATES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported queue status"
                ),
                "allowed": list(
                    CLOSED_LOOP_STATES
                ),
            },
        )

    if (
        priority is not None
        and priority
        not in CLOSED_LOOP_PRIORITIES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported queue priority"
                ),
                "allowed": list(
                    CLOSED_LOOP_PRIORITIES
                ),
            },
        )

    if (
        recommendation_type is not None
        and recommendation_type
        not in CLOSED_LOOP_RECOMMENDATION_TYPES
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Unsupported recommendation type"
                ),
                "allowed": list(
                    CLOSED_LOOP_RECOMMENDATION_TYPES
                ),
            },
        )

    experiment_id, run = (
        _resolve_vehicle_twin_run(
            db,
            run_id,
        )
    )

    persisted = (
        _decision_queue_persisted_rows(
            db,
            run=run,
            experiment_id=experiment_id,
        )
    )

    inputs = []

    for row in persisted:
        if (
            status is not None
            and row.status != status
        ):
            continue

        if (
            priority is not None
            and row.priority != priority
        ):
            continue

        if (
            recommendation_type
            is not None
            and row.recommendation_type
            != recommendation_type
        ):
            continue

        if (
            assigned_to is not None
            and row.assigned_to
            != assigned_to
        ):
            continue

        if (
            unassigned is True
            and row.assigned_to
        ):
            continue

        if (
            unassigned is False
            and not row.assigned_to
        ):
            continue

        inputs.append(
            _decision_queue_input(
                row
            )
        )

    now = datetime.now(
        timezone.utc
    )

    rows = decision_queue_rows(
        inputs,
        now=now,
        include_terminal=(
            include_terminal
        ),
    )

    selected = rows[:limit]

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            DECISION_QUEUE_RULES_VERSION
        ),
        "totalMatched": len(rows),
        "returned": len(selected),
        "queue": selected,
        "scopePolicy": (
            _decision_queue_scope_policy()
        ),
        "generatedAt": (
            now.isoformat()
        ),
    }


@router.get(
    "/decision-queue/{recommendation_id}"
)
def decision_queue_detail(
    recommendation_id: int,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, row = (
        _closed_loop_selected_recommendation(
            db,
            recommendation_id=(
                recommendation_id
            ),
            run_id=run_id,
        )
    )

    activities = db.execute(
        select(
            DiagnosticOperationalRecommendationActivity
        )
        .where(
            DiagnosticOperationalRecommendationActivity.recommendation_id
            == row.id,
            DiagnosticOperationalRecommendationActivity.run_id
            == run.id,
            DiagnosticOperationalRecommendationActivity.experiment_id
            == experiment_id,
        )
        .order_by(
            DiagnosticOperationalRecommendationActivity.created_at,
            DiagnosticOperationalRecommendationActivity.id,
        )
    ).scalars().all()

    queue_row = decision_queue_rows(
        [
            _decision_queue_input(
                row
            )
        ],
        now=datetime.now(
            timezone.utc
        ),
        include_terminal=True,
    )[0]

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "lineage": run.lineage,
        "rulesVersion": (
            DECISION_QUEUE_RULES_VERSION
        ),
        "queueRecord": queue_row,
        "recommendation": (
            _closed_loop_recommendation_payload(
                row
            )
        ),
        "allowedNextStates": list(
            allowed_next_states(
                row.status
            )
        ),
        "assignmentAllowed": (
            assignment_allowed(
                row.status
            )
        ),
        "activities": [
            _closed_loop_activity_payload(
                activity
            )
            for activity in activities
        ],
        "scopePolicy": (
            _decision_queue_scope_policy()
        ),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@router.post(
    "/decision-queue/{recommendation_id}/assign"
)
def decision_queue_assign(
    recommendation_id: int,
    request: DecisionQueueAssignmentRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    experiment_id, run, row = (
        _closed_loop_selected_recommendation(
            db,
            recommendation_id=(
                recommendation_id
            ),
            run_id=run_id,
        )
    )

    if not assignment_allowed(
        row.status
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Assignment cannot be changed "
                "after the recommendation reaches "
                "a terminal lifecycle state."
            ),
        )

    target = (
        request.assignedTo.strip()
        if request.assignedTo
        and request.assignedTo.strip()
        else None
    )

    previous = row.assigned_to

    if previous == target:
        return {
            "runId": run.id,
            "experimentId": experiment_id,
            "rulesVersion": (
                DECISION_QUEUE_RULES_VERSION
            ),
            "changed": False,
            "recommendation": (
                _closed_loop_recommendation_payload(
                    row
                )
            ),
            "scopePolicy": (
                _decision_queue_scope_policy()
            ),
        }

    now = datetime.now(
        timezone.utc
    )

    row.assigned_to = target
    row.assigned_at = (
        now
        if target is not None
        else None
    )
    row.updated_at = now
    row.last_actor = request.actor

    _closed_loop_add_activity(
        db,
        recommendation=row,
        activity_type=(
            "ASSIGNED"
            if target is not None
            else "UNASSIGNED"
        ),
        actor=request.actor,
        from_state=row.status,
        to_state=row.status,
        note=request.note,
        created_at=now,
        details={
            "previousAssignee": previous,
            "assignedTo": target,
            "workflowMetadataOnly": True,
            "diagnosticEvidenceModified": False,
            "physicalAction": False,
        },
    )

    db.commit()
    db.refresh(row)

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "rulesVersion": (
            DECISION_QUEUE_RULES_VERSION
        ),
        "changed": True,
        "recommendation": (
            _closed_loop_recommendation_payload(
                row
            )
        ),
        "scopePolicy": (
            _decision_queue_scope_policy()
        ),
        "interpretationPolicy": (
            "Assignment changes recommendation "
            "ownership metadata only. Diagnostic "
            "evidence, model output and physical "
            "vehicle state are unchanged."
        ),
    }


def _decision_queue_transition(
    db: Session,
    *,
    recommendation_id: int,
    run_id: int | None,
    request: ClosedLoopTransitionRequest,
    target_state: str,
    activity_type: str,
) -> dict:
    result = (
        _closed_loop_transition_response(
            db,
            recommendation_id=(
                recommendation_id
            ),
            run_id=run_id,
            request=request,
            target_state=target_state,
            activity_type=activity_type,
        )
    )

    result["decisionQueueRulesVersion"] = (
        DECISION_QUEUE_RULES_VERSION
    )

    result["queueScopePolicy"] = (
        _decision_queue_scope_policy()
    )

    return result


@router.post(
    "/decision-queue/{recommendation_id}/acknowledge"
)
def decision_queue_acknowledge(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _decision_queue_transition(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_ACKNOWLEDGED,
        activity_type="ACKNOWLEDGED",
    )


@router.post(
    "/decision-queue/{recommendation_id}/request-approval"
)
def decision_queue_request_approval(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _decision_queue_transition(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=(
            STATE_APPROVAL_REQUIRED
        ),
        activity_type=(
            "APPROVAL_REQUESTED"
        ),
    )


@router.post(
    "/decision-queue/{recommendation_id}/approve"
)
def decision_queue_approve(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _decision_queue_transition(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_APPROVED,
        activity_type="APPROVED",
    )


@router.post(
    "/decision-queue/{recommendation_id}/mark-execution-ready"
)
def decision_queue_mark_execution_ready(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _decision_queue_transition(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=(
            STATE_EXECUTION_READY
        ),
        activity_type="EXECUTION_READY",
    )


@router.post(
    "/decision-queue/{recommendation_id}/execute"
)
def decision_queue_execute(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _decision_queue_transition(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_EXECUTED,
        activity_type="EXECUTED",
    )


@router.post(
    "/decision-queue/{recommendation_id}/reject"
)
def decision_queue_reject(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _decision_queue_transition(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_REJECTED,
        activity_type="REJECTED",
    )


@router.post(
    "/decision-queue/{recommendation_id}/cancel"
)
def decision_queue_cancel(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _decision_queue_transition(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_CANCELLED,
        activity_type="CANCELLED",
    )


@router.post(
    "/decision-queue/{recommendation_id}/supersede"
)
def decision_queue_supersede(
    recommendation_id: int,
    request: ClosedLoopTransitionRequest,
    run_id: int | None = Query(
        default=None,
        ge=1,
    ),
    db: Session = Depends(db_session),
) -> dict:
    return _decision_queue_transition(
        db,
        recommendation_id=(
            recommendation_id
        ),
        run_id=run_id,
        request=request,
        target_state=STATE_SUPERSEDED,
        activity_type="SUPERSEDED",
    )
