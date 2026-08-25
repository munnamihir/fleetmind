from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from fleetmind_common.db import SessionLocal
from fleetmind_common.diagnostic_store import DiagnosticModelRun, DiagnosticPrediction
from fleetmind_common.models import Telemetry


router = APIRouter(
    prefix="/api/v1/diagnostics",
    tags=["diagnostics"],
)


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
