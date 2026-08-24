from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from fleetmind_common.db import Base, SessionLocal, engine
from fleetmind_common.models import Alert, Telemetry

app = FastAPI(title="FleetMind API", version="0.1.0")
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "fleetmind-api"}


@app.get("/api/v1/fleet/summary")
def fleet_summary(db: Session = Depends(db_session)) -> dict:
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    latest = (
        select(
            Telemetry.vehicle_id,
            func.max(Telemetry.id).label("max_id"),
        )
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

    active_alerts = db.scalar(
        select(func.count(Alert.id)).where(Alert.created_at >= since)
    ) or 0
    critical_alerts = db.scalar(
        select(func.count(Alert.id)).where(
            Alert.created_at >= since,
            Alert.severity == "critical",
        )
    ) or 0
    telemetry_events = db.scalar(select(func.count(Telemetry.id))) or 0

    total = len(rows)
    return {
        "vehiclesMonitored": total,
        "telemetryEvents": telemetry_events,
        "activeAlerts": active_alerts,
        "criticalAlerts": critical_alerts,
        "averageRisk": round(risk_total / total, 4) if total else 0.0,
        "health": counts,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/alerts")
def alerts(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(db_session),
) -> list[dict]:
    rows = db.execute(
        select(Alert).order_by(desc(Alert.created_at)).limit(limit)
    ).scalars().all()
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

    return {
        "vehicleId": latest.vehicle_id,
        "model": latest.model,
        "factory": latest.factory,
        "firmware": latest.firmware,
        "pumpRevision": latest.pump_revision,
        "mileage": latest.mileage,
        "status": latest.status,
        "riskScore": latest.risk_score,
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
                "riskScore": h.risk_score,
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
