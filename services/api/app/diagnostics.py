from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from fleetmind_common.db import SessionLocal
from fleetmind_common.diagnostic_event_rules import (
    DIAGNOSTIC_EVENT_TYPES,
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
    DiagnosticCase,
    DiagnosticCaseActivity,
    DiagnosticInvestigationView,
    DiagnosticWatchlistEntry,
    DiagnosticEpisode,
    DiagnosticEvent,
    DiagnosticModelRun,
    DiagnosticPrediction,
    DiagnosticReplayPoint,
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
