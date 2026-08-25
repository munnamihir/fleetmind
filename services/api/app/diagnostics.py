from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from fleetmind_common.db import SessionLocal
from fleetmind_common.diagnostic_store import (
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
