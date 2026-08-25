from __future__ import annotations

from collections import defaultdict
import json
import os
from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from fleetmind_common.db import Base, SessionLocal, engine
from fleetmind_common.models import Alert, FailureEvent, MLModelRun, MLPrediction, Telemetry
from fleetmind_common.firmware import FirmwareObservation, compare_firmware, hardware_interactions
from fleetmind_common.reliability import (
    ReliabilityObservation,
    fit_weibull_right_censored,
    kaplan_meier,
    median_or_none,
)

app = FastAPI(title="FleetMind API", version="0.6.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def latest_vehicle_rows(db: Session) -> list[Telemetry]:
    latest = (
        select(Telemetry.vehicle_id, func.max(Telemetry.id).label("max_id"))
        .group_by(Telemetry.vehicle_id)
        .subquery()
    )
    return db.execute(
        select(Telemetry).join(latest, Telemetry.id == latest.c.max_id)
    ).scalars().all()



def firmware_observations(db: Session) -> list[FirmwareObservation]:
    latest_rows = latest_vehicle_rows(db)
    failed_vehicle_ids = set(db.execute(select(FailureEvent.vehicle_id)).scalars().all())
    return [
        FirmwareObservation(
            firmware=row.firmware,
            pump_revision=row.pump_revision,
            factory=row.factory,
            model=row.model,
            mileage=float(row.mileage),
            ambient_temp_c=float(row.ambient_temp_c),
            failed=row.vehicle_id in failed_vehicle_ids,
            risk_score=float(row.risk_score),
            non_healthy=row.status != "healthy",
            pump_current_a=float(row.pump_current_a),
        )
        for row in latest_rows
    ]


def _round_nested(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [_round_nested(item) for item in value]
    if isinstance(value, dict):
        return {key: _round_nested(item) for key, item in value.items()}
    return value

def warning_metrics(db: Session, failure: FailureEvent) -> dict:
    warning = db.execute(
        select(Telemetry)
        .where(
            Telemetry.vehicle_id == failure.vehicle_id,
            Telemetry.status != "healthy",
            Telemetry.timestamp <= failure.occurred_at,
        )
        .order_by(Telemetry.timestamp)
        .limit(1)
    ).scalar_one_or_none()

    if warning is None:
        return {
            "detectedBeforeFailure": False,
            "firstWarningAt": None,
            "warningMileage": None,
            "leadMiles": None,
            "leadSeconds": None,
            "leadSimulatedHours": None,
            "leadSimulatedDays": None,
        }

    lead_miles = max(0.0, failure.failure_mileage - warning.mileage)
    lead_seconds = max(0.0, (failure.occurred_at - warning.timestamp).total_seconds())
    simulated_hours = lead_seconds * failure.simulation_time_acceleration / 3600.0
    return {
        "detectedBeforeFailure": warning.timestamp < failure.occurred_at,
        "firstWarningAt": warning.timestamp.isoformat(),
        "warningMileage": round(warning.mileage, 1),
        "leadMiles": round(lead_miles, 1),
        "leadSeconds": round(lead_seconds, 2),
        "leadSimulatedHours": round(simulated_hours, 2),
        "leadSimulatedDays": round(simulated_hours / 24.0, 3),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "fleetmind-api", "version": "0.4.0"}


@app.get("/api/v1/fleet/summary")
def fleet_summary(db: Session = Depends(db_session)) -> dict:
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    latest = (
        select(Telemetry.vehicle_id, func.max(Telemetry.id).label("max_id"))
        .where(Telemetry.timestamp >= since)
        .group_by(Telemetry.vehicle_id)
        .subquery()
    )
    rows = db.execute(
        select(Telemetry).join(latest, Telemetry.id == latest.c.max_id)
    ).scalars().all()

    counts = {"healthy": 0, "degraded": 0, "critical": 0}
    risk_total = 0.0
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
        risk_total += row.risk_score

    active_alerts = db.scalar(select(func.count(Alert.id)).where(Alert.created_at >= since)) or 0
    critical_alerts = db.scalar(
        select(func.count(Alert.id)).where(Alert.created_at >= since, Alert.severity == "critical")
    ) or 0
    telemetry_events = db.scalar(select(func.count(Telemetry.id))) or 0
    failures = db.scalar(select(func.count(FailureEvent.id))) or 0

    total = len(rows)
    return {
        "vehiclesMonitored": total,
        "telemetryEvents": telemetry_events,
        "activeAlerts": active_alerts,
        "criticalAlerts": critical_alerts,
        "observedFailures": failures,
        "averageRisk": round(risk_total / total, 4) if total else 0.0,
        "health": counts,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/alerts")
def alerts(limit: int = Query(default=20, ge=1, le=200), db: Session = Depends(db_session)) -> list[dict]:
    rows = db.execute(select(Alert).order_by(desc(Alert.created_at)).limit(limit)).scalars().all()
    return [
        {
            "id": row.id,
            "createdAt": row.created_at.isoformat(),
            "vehicleId": row.vehicle_id,
            "severity": row.severity,
            "riskScore": row.risk_score,
            "title": row.title,
            "evidence": row.evidence.split(" | ") if row.evidence else [],
            "firmware": row.firmware,
            "pumpRevision": row.pump_revision,
            "factory": row.factory,
        }
        for row in rows
    ]


@app.get("/api/v1/vehicles/{vehicle_id}")
def vehicle(vehicle_id: str, db: Session = Depends(db_session)) -> dict:
    latest = db.execute(
        select(Telemetry)
        .where(Telemetry.vehicle_id == vehicle_id)
        .order_by(desc(Telemetry.timestamp))
        .limit(1)
    ).scalar_one_or_none()
    if latest is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    history = db.execute(
        select(Telemetry)
        .where(Telemetry.vehicle_id == vehicle_id)
        .order_by(desc(Telemetry.timestamp))
        .limit(60)
    ).scalars().all()
    history.reverse()

    failure = db.execute(
        select(FailureEvent).where(FailureEvent.vehicle_id == vehicle_id)
    ).scalar_one_or_none()

    return {
        "vehicleId": latest.vehicle_id,
        "model": latest.model,
        "factory": latest.factory,
        "firmware": latest.firmware,
        "pumpRevision": latest.pump_revision,
        "mileage": latest.mileage,
        "status": latest.status,
        "riskScore": latest.risk_score,
        "failure": (
            {
                "occurredAt": failure.occurred_at.isoformat(),
                "mileage": failure.failure_mileage,
                "component": failure.component,
                "failureMode": failure.failure_mode,
                "faultCode": failure.fault_code,
                "warning": warning_metrics(db, failure),
            }
            if failure
            else None
        ),
        "latest": {
            "timestamp": latest.timestamp.isoformat(),
            "batteryTempC": latest.battery_temp_c,
            "coolantTempC": latest.coolant_temp_c,
            "pumpRPM": latest.pump_rpm,
            "pumpCurrentA": latest.pump_current_a,
            "cellImbalanceV": latest.cell_imbalance_v,
        },
        "history": [
            {
                "timestamp": h.timestamp.isoformat(),
                "mileage": h.mileage,
                "riskScore": h.risk_score,
                "status": h.status,
                "batteryTempC": h.battery_temp_c,
                "pumpCurrentA": h.pump_current_a,
                "pumpRPM": h.pump_rpm,
            }
            for h in history
        ],
    }


@app.get("/api/v1/cohorts/pump-revisions")
def pump_revision_cohorts(db: Session = Depends(db_session)) -> list[dict]:
    rows = db.execute(
        select(
            Telemetry.pump_revision,
            func.count(Telemetry.id),
            func.avg(Telemetry.risk_score),
            func.avg(Telemetry.pump_current_a),
        ).group_by(Telemetry.pump_revision)
    ).all()
    return [
        {
            "pumpRevision": revision,
            "samples": samples,
            "averageRisk": round(float(avg_risk or 0), 4),
            "averagePumpCurrentA": round(float(avg_current or 0), 3),
        }
        for revision, samples, avg_risk, avg_current in rows
    ]


@app.get("/api/v1/reliability/pump-revisions")
def pump_reliability(db: Session = Depends(db_session)) -> list[dict]:
    latest_rows = latest_vehicle_rows(db)
    failures = db.execute(select(FailureEvent)).scalars().all()
    failures_by_vehicle = {f.vehicle_id: f for f in failures}

    cohorts: dict[str, list[Telemetry]] = defaultdict(list)
    for row in latest_rows:
        cohorts[row.pump_revision].append(row)

    response: list[dict] = []
    for revision in sorted(cohorts):
        vehicle_rows = cohorts[revision]
        observations: list[ReliabilityObservation] = []
        cohort_failures: list[FailureEvent] = []

        for row in vehicle_rows:
            failure = failures_by_vehicle.get(row.vehicle_id)
            if failure is not None:
                observations.append(ReliabilityObservation(failure.failure_mileage, True))
                cohort_failures.append(failure)
            else:
                observations.append(ReliabilityObservation(row.mileage, False))

        fit = fit_weibull_right_censored(observations)
        warning_rows = [warning_metrics(db, failure) for failure in cohort_failures]
        detected = [w for w in warning_rows if w["detectedBeforeFailure"]]
        lead_miles = [float(w["leadMiles"]) for w in detected if w["leadMiles"] is not None]
        lead_seconds = [float(w["leadSeconds"]) for w in detected if w["leadSeconds"] is not None]
        lead_sim_days = [float(w["leadSimulatedDays"]) for w in detected if w["leadSimulatedDays"] is not None]

        km = kaplan_meier(observations)
        # Keep API payload compact for large fleets while preserving curve shape.
        if len(km) > 80:
            stride = max(1, len(km) // 79)
            sampled = km[::stride]
            if sampled[-1] != km[-1]:
                sampled.append(km[-1])
            km = sampled

        weibull = None
        if fit is not None:
            weibull = {
                "beta": round(fit.beta, 4),
                "etaMiles": round(fit.eta, 1),
                "b10Miles": round(fit.b10, 1),
                "b50Miles": round(fit.b50, 1),
                "failureBehavior": fit.failure_behavior,
                "reliability": {
                    str(miles): round(fit.reliability(float(miles)), 6)
                    for miles in (25000, 50000, 75000, 100000)
                },
            }

        response.append(
            {
                "pumpRevision": revision,
                "population": len(vehicle_rows),
                "failures": len(cohort_failures),
                "censored": len(vehicle_rows) - len(cohort_failures),
                "failureRate": round(len(cohort_failures) / len(vehicle_rows), 6) if vehicle_rows else 0.0,
                "weibull": weibull,
                "earlyWarning": {
                    "failuresEvaluated": len(cohort_failures),
                    "detectedBeforeFailure": len(detected),
                    "detectionRate": round(len(detected) / len(cohort_failures), 6) if cohort_failures else None,
                    "medianLeadMiles": round(median_or_none(lead_miles), 1) if lead_miles else None,
                    "medianLeadSeconds": round(median_or_none(lead_seconds), 2) if lead_seconds else None,
                    "medianLeadSimulatedDays": round(median_or_none(lead_sim_days), 3) if lead_sim_days else None,
                },
                "kaplanMeier": km,
            }
        )

    return response


@app.get("/api/v1/reliability/failures")
def reliability_failures(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(db_session),
) -> list[dict]:
    rows = db.execute(
        select(FailureEvent).order_by(desc(FailureEvent.occurred_at)).limit(limit)
    ).scalars().all()
    return [
        {
            "vehicleId": row.vehicle_id,
            "occurredAt": row.occurred_at.isoformat(),
            "failureMileage": row.failure_mileage,
            "component": row.component,
            "failureMode": row.failure_mode,
            "faultCode": row.fault_code,
            "model": row.model,
            "factory": row.factory,
            "firmware": row.firmware,
            "pumpRevision": row.pump_revision,
            "warning": warning_metrics(db, row),
        }
        for row in rows
    ]


@app.get("/api/v1/firmware/regression")
def firmware_regression(
    target: str = Query(default="2026.32.4"),
    control: str = Query(default="2026.32.1"),
    db: Session = Depends(db_session),
) -> dict:
    if target == control:
        raise HTTPException(status_code=400, detail="target and control firmware must differ")

    observations = firmware_observations(db)
    firmwares = sorted({item.firmware for item in observations})
    if target not in firmwares:
        raise HTTPException(status_code=404, detail=f"Target firmware {target} not found")
    if control not in firmwares:
        raise HTTPException(status_code=404, detail=f"Control firmware {control} not found")

    comparison = compare_firmware(observations, target, control)
    interactions = hardware_interactions(observations, target, control)

    return _round_nested(
        {
            **comparison,
            "hardwareInteractions": interactions,
            "availableFirmware": firmwares,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "interpretation": {
                "method": "Coarsened exact matching + Cochran-Mantel-Haenszel association test",
                "claimPolicy": "Regression labels require a matched population of at least 30 vehicles and at least 2 observed failures.",
                "telemetrySignalsAreSupportive": True,
            },
        }
    )


@app.get("/api/v1/firmware/overview")
def firmware_overview(db: Session = Depends(db_session)) -> list[dict]:
    observations = firmware_observations(db)
    rows: list[dict] = []
    for firmware in sorted({item.firmware for item in observations}):
        scoped = [item for item in observations if item.firmware == firmware]
        population = len(scoped)
        failures = sum(1 for item in scoped if item.failed)
        rows.append(
            {
                "firmware": firmware,
                "population": population,
                "failures": failures,
                "failureRate": round(failures / population, 6) if population else 0.0,
                "averageRisk": round(sum(item.risk_score for item in scoped) / population, 6) if population else 0.0,
                "nonHealthyRate": round(sum(1 for item in scoped if item.non_healthy) / population, 6) if population else 0.0,
                "averagePumpCurrentA": round(sum(item.pump_current_a for item in scoped) / population, 4) if population else 0.0,
            }
        )
    return rows



def _json_or(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


DEFAULT_MODEL_LINEAGE = os.getenv("ML_MODEL_LINEAGE", "fm-ml-5.2-v1")


def _run_lineage(run: MLModelRun) -> str:
    metrics = _json_or(run.metrics_json, {})
    policy = _json_or(run.leakage_policy_json, {})
    return str(metrics.get("modelLineage") or policy.get("modelLineage") or "legacy")


def _latest_run(db: Session) -> MLModelRun | None:
    return db.execute(
        select(MLModelRun)
        .order_by(desc(MLModelRun.created_at), desc(MLModelRun.id))
        .limit(1)
    ).scalar_one_or_none()


def _active_model_lineage(db: Session) -> str:
    latest = _latest_run(db)
    if latest is None:
        return DEFAULT_MODEL_LINEAGE
    lineage = _run_lineage(latest)
    return DEFAULT_MODEL_LINEAGE if lineage == "legacy" else lineage


def _latest_complete_run_for_lineage(
    db: Session, lineage: str
) -> MLModelRun | None:
    # Lineage lives in JSON for backward compatibility with Phase 5 tables, so
    # filter a bounded recent set in Python instead of returning a stale legacy
    # model just because it is the newest row with status=complete.
    candidates = db.execute(
        select(MLModelRun)
        .where(MLModelRun.status == "complete")
        .order_by(desc(MLModelRun.completed_at), desc(MLModelRun.id))
        .limit(500)
    ).scalars().all()
    return next((run for run in candidates if _run_lineage(run) == lineage), None)


def _model_run_payload(run: MLModelRun) -> dict:
    metrics = _json_or(run.metrics_json, {})
    benchmark = {"examples": run.test_examples, "positives": run.test_positives}
    return {
        "runId": run.id,
        "createdAt": run.created_at.isoformat(),
        "completedAt": run.completed_at.isoformat() if run.completed_at else None,
        "status": run.status,
        "algorithm": run.algorithm,
        "horizonMiles": run.horizon_miles,
        "windowSize": run.window_size,
        "dataset": {
            "train": {"examples": run.train_examples, "positives": run.train_positives},
            "validation": {"examples": run.validation_examples, "positives": run.validation_positives},
            "benchmark": benchmark,
            # Backward-compatible alias for Phase 5 clients.
            "test": benchmark,
        },
        "decisionThreshold": run.decision_threshold,
        "metrics": metrics,
        "modelLineage": metrics.get("modelLineage") or _json_or(run.leakage_policy_json, {}).get("modelLineage"),
        "benchmarkQualification": metrics.get("benchmarkQualification"),
        "benchmarkSnapshot": metrics.get("benchmarkSnapshot") or _json_or(run.leakage_policy_json, {}).get("benchmarkSnapshot"),
        "baseline": metrics.get("baseline"),
        "modelDeltaVsBaseline": metrics.get("modelDeltaVsBaseline"),
        "benchmarkProtocol": metrics.get("benchmarkProtocol"),
        "operationalScoring": metrics.get("operationalScoring"),
        "calibration": _json_or(run.calibration_json, []),
        "featureImportance": _json_or(run.feature_importance_json, []),
        "leakagePolicy": _json_or(run.leakage_policy_json, {}),
        "notes": run.notes,
    }


@app.get("/api/v1/ml/status")
def ml_status(db: Session = Depends(db_session)) -> dict:
    run = _latest_run(db)
    if run is None:
        return {
            "status": "waiting_for_trainer",
            "message": "No predictive-maintenance training run has been recorded yet.",
            "modelLineage": DEFAULT_MODEL_LINEAGE,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
    return {
        **_model_run_payload(run),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/ml/benchmark")
def ml_benchmark(db: Session = Depends(db_session)) -> dict:
    # The benchmark endpoint represents the *active* model lineage, including
    # its accumulating/insufficient-data state. Never fall back to an older
    # complete lineage while the current trainer is waiting for valid labels.
    run = _latest_run(db)
    if run is None:
        return {
            "status": "waiting_for_trainer",
            "message": "No predictive-maintenance run is available yet.",
            "modelLineage": DEFAULT_MODEL_LINEAGE,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }

    payload = _model_run_payload(run)
    if run.status != "complete":
        return {
            "runId": run.id,
            "status": run.status,
            "message": run.notes or "Current model lineage is still accumulating causal training evidence.",
            "qualification": payload.get("benchmarkQualification"),
            "snapshot": payload.get("benchmarkSnapshot"),
            "modelLineage": payload.get("modelLineage") or _run_lineage(run),
            "protocol": payload.get("benchmarkProtocol"),
            "dataset": payload.get("dataset"),
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "runId": run.id,
        "status": payload.get("benchmarkQualification", {}).get("status", "legacy_run"),
        "qualification": payload.get("benchmarkQualification"),
        "snapshot": payload.get("benchmarkSnapshot"),
        "modelLineage": payload.get("modelLineage"),
        "protocol": payload.get("benchmarkProtocol"),
        "xgboost": payload.get("metrics"),
        "baseline": payload.get("baseline"),
        "deltaVsBaseline": payload.get("modelDeltaVsBaseline"),
        "dataset": payload.get("dataset"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/ml/predictions")
def ml_predictions(
    limit: int = Query(default=25, ge=1, le=500),
    db: Session = Depends(db_session),
) -> list[dict]:
    active_lineage = _active_model_lineage(db)
    run = _latest_complete_run_for_lineage(db, active_lineage)
    if run is None:
        return []

    rows = db.execute(
        select(MLPrediction)
        .where(MLPrediction.model_run_id == run.id)
        .order_by(desc(MLPrediction.probability))
        .limit(limit)
    ).scalars().all()
    return [
        {
            "modelRunId": row.model_run_id,
            "generatedAt": row.generated_at.isoformat(),
            "vehicleId": row.vehicle_id,
            "probability": row.probability,
            "predictedFailureWithinHorizon": bool(row.predicted_label),
            "anchorMileage": row.anchor_mileage,
            "firmware": row.firmware,
            "pumpRevision": row.pump_revision,
            "factory": row.factory,
            "model": row.model,
            "featureSummary": _json_or(row.feature_summary_json, {}),
            "horizonMiles": run.horizon_miles,
            "decisionThreshold": run.decision_threshold,
        }
        for row in rows
    ]


@app.get("/api/v1/ml/vehicles/{vehicle_id}")
def ml_vehicle_prediction(vehicle_id: str, db: Session = Depends(db_session)) -> dict:
    active_lineage = _active_model_lineage(db)
    run = _latest_complete_run_for_lineage(db, active_lineage)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail=f"No complete ML prediction is available for active lineage {active_lineage}",
        )
    row = db.execute(
        select(MLPrediction)
        .where(
            MLPrediction.vehicle_id == vehicle_id,
            MLPrediction.model_run_id == run.id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No current-lineage ML prediction available for vehicle")
    return {
        "vehicleId": row.vehicle_id,
        "probability": row.probability,
        "predictedFailureWithinHorizon": bool(row.predicted_label),
        "generatedAt": row.generated_at.isoformat(),
        "anchorMileage": row.anchor_mileage,
        "firmware": row.firmware,
        "pumpRevision": row.pump_revision,
        "factory": row.factory,
        "model": row.model,
        "featureSummary": _json_or(row.feature_summary_json, {}),
        "modelRun": _model_run_payload(run) if run else None,
    }

@app.get("/api/v1/ml/vehicles/{vehicle_id}/history")
def ml_vehicle_prediction_history(
    vehicle_id: str,
    limit: int = Query(default=60, ge=2, le=250),
    include_legacy: bool = Query(default=False, alias="includeLegacy"),
    db: Session = Depends(db_session),
) -> dict:
    raw_rows = db.execute(
        select(MLPrediction, MLModelRun)
        .join(MLModelRun, MLModelRun.id == MLPrediction.model_run_id)
        .where(
            MLPrediction.vehicle_id == vehicle_id,
            MLModelRun.status == "complete",
        )
        .order_by(desc(MLPrediction.generated_at), desc(MLPrediction.id))
        .limit(1000)
    ).all()
    if not raw_rows:
        raise HTTPException(status_code=404, detail="No ML prediction history available for vehicle")

    def lineage(run: MLModelRun) -> str:
        policy = _json_or(run.leakage_policy_json, {})
        return str(policy.get("modelLineage") or "legacy")

    latest_lineage = _active_model_lineage(db)
    lineage_rows = (
        raw_rows
        if include_legacy
        else [row for row in raw_rows if lineage(row[1]) == latest_lineage]
    )
    excluded_lineage = len(raw_rows) - len(lineage_rows)

    chronological = list(reversed(lineage_rows))
    epoch_start = 0
    if not include_legacy:
        for index in range(1, len(chronological)):
            previous = chronological[index - 1][0]
            current = chronological[index][0]
            if previous.anchor_mileage - current.anchor_mileage > 50.0:
                epoch_start = index
    epoch_rows = chronological[epoch_start:]
    excluded_epoch = len(chronological) - len(epoch_rows)
    epoch_rows = epoch_rows[-limit:]

    points = [
        {
            "modelRunId": prediction.model_run_id,
            "modelLineage": lineage(run),
            "generatedAt": prediction.generated_at.isoformat(),
            "anchorMileage": prediction.anchor_mileage,
            "probability": prediction.probability,
            "decisionThreshold": run.decision_threshold,
            "predictedFailureWithinHorizon": bool(prediction.predicted_label),
            "firmware": prediction.firmware,
            "pumpRevision": prediction.pump_revision,
        }
        for prediction, run in epoch_rows
    ]
    if not points:
        raise HTTPException(status_code=404, detail="No comparable ML prediction history available for vehicle")

    return {
        "vehicleId": vehicle_id,
        "modelLineage": latest_lineage if not include_legacy else "mixed",
        "includeLegacy": include_legacy,
        "points": points,
        "latest": points[-1],
        "historyPolicy": {
            "sameModelLineageOnly": not include_legacy,
            "latestMileageEpochOnly": not include_legacy,
            "mileageResetDropMiles": 50.0,
            "excludedPriorLineagePoints": excluded_lineage,
            "excludedPriorEpochPoints": excluded_epoch,
            "continuousPlotSafe": not include_legacy,
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
