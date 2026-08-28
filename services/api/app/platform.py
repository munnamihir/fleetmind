"""FleetMind Phase 9 platform API: SLOs, model ops and multi-asset views."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleetmind_common.asset_plugins import (
    ASSET_PLUGIN_RULES_VERSION,
    plugin_catalog,
    score_asset_event,
    validate_asset_event,
)
from fleetmind_common.db import SessionLocal
from fleetmind_common.diagnostic_store import DiagnosticModelRun
from fleetmind_common.model_ops_rules import (
    MODEL_OPS_RULES_VERSION,
    MODEL_STAGES,
    distribution_stats,
    drift_report,
    promotion_readiness,
)
from fleetmind_common.models import Telemetry
from fleetmind_common.platform_store import (
    AssetTelemetryRecord,
    DiagnosticModelRegistryEntry,
    DiagnosticPolicyEvaluation,
    DiagnosticRecommendationOutcome,
    DiagnosticRecommendationPolicy,
    DiagnosticShadowExperiment,
)


router = APIRouter(
    prefix="/api/v1/platform",
    tags=["platform"],
)


SLO_DEFINITIONS = {
    "version": "fm-slo-9.1-v1",
    "measurementOnly": True,
    "objectives": [
        {
            "name": "api_availability",
            "target": 0.995,
            "window": "30d",
            "indicator": "non-5xx HTTP responses / all HTTP responses",
        },
        {
            "name": "api_latency_p95",
            "targetSeconds": 0.75,
            "window": "24h",
            "indicator": "95th percentile API request latency",
        },
        {
            "name": "db_pool_saturation",
            "target": 0.80,
            "window": "5m",
            "indicator": "checked-out DB connections / available pool capacity",
        },
        {
            "name": "ingestion_freshness",
            "targetSeconds": 30.0,
            "window": "5m",
            "indicator": "age of most recent persisted telemetry",
        },
    ],
    "claimBoundary": {
        "objectivesAreTargets": True,
        "objectivesAreNotClaimedAsAchieved": True,
    },
}


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _active_experiment_id(db: Session) -> str | None:
    return db.execute(
        select(Telemetry.experiment_id)
        .where(Telemetry.experiment_id.is_not(None))
        .order_by(desc(Telemetry.id))
        .limit(1)
    ).scalar_one_or_none()


def _latest_diagnostic_run(db: Session) -> DiagnosticModelRun | None:
    experiment_id = _active_experiment_id(db)
    statement = select(DiagnosticModelRun)
    if experiment_id is not None:
        statement = statement.where(
            DiagnosticModelRun.experiment_id == experiment_id
        )
    return db.execute(
        statement.order_by(
            desc(DiagnosticModelRun.created_at),
            desc(DiagnosticModelRun.id),
        ).limit(1)
    ).scalar_one_or_none()


def _latest_vehicle_telemetry(db: Session) -> list[Telemetry]:
    experiment_id = _active_experiment_id(db)
    statement = select(
        Telemetry.vehicle_id,
        func.max(Telemetry.id).label("max_id"),
    )
    if experiment_id is not None:
        statement = statement.where(Telemetry.experiment_id == experiment_id)
    latest = statement.group_by(Telemetry.vehicle_id).subquery()
    return db.execute(
        select(Telemetry).join(latest, Telemetry.id == latest.c.max_id)
    ).scalars().all()


MODEL_BASELINE_FEATURES = (
    "pump_current_a",
    "pump_rpm",
    "coolant_temp_c",
    "battery_temp_c",
    "cell_imbalance_v",
    "inverter_temp_c",
)


def _feature_baseline(
    rows: list[Telemetry],
    features: list[str] | None = None,
) -> dict[str, dict[str, float | int | None]]:
    selected = features or list(MODEL_BASELINE_FEATURES)
    result = {}
    for feature in selected:
        values = []
        for row in rows:
            if not hasattr(row, feature):
                continue
            value = getattr(row, feature)
            if isinstance(value, (int, float)):
                values.append(float(value))
        result[feature] = distribution_stats(values)
    return result


def _registry_payload(row: DiagnosticModelRegistryEntry) -> dict[str, Any]:
    return {
        "id": row.id,
        "modelName": row.model_name,
        "version": row.version,
        "lineage": row.lineage,
        "sourceRunId": row.source_run_id,
        "stage": row.stage,
        "artifactUri": row.artifact_uri,
        "artifactSha256": row.artifact_sha256,
        "featureSchemaSha256": row.feature_schema_sha256,
        "benchmarkSnapshotSha256": row.benchmark_snapshot_sha256,
        "benchmarkStatus": row.benchmark_status,
        "metrics": _json_object(row.metrics_json),
        "featureBaseline": _json_object(row.feature_baseline_json),
        "createdAt": row.created_at.isoformat(),
        "createdBy": row.created_by,
        "promotedAt": row.promoted_at.isoformat() if row.promoted_at else None,
        "promotedBy": row.promoted_by,
        "externalSync": _json_object(row.external_sync_json),
        "notes": row.notes,
    }


def _external_registry_sync(payload: dict[str, Any]) -> dict[str, Any]:
    base_url = os.getenv("MODEL_REGISTRY_URL", "").strip()
    if not base_url:
        return {
            "configured": False,
            "synced": False,
            "message": "MODEL_REGISTRY_URL is not configured",
        }

    url = base_url.rstrip("/") + "/models"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    token = os.getenv("MODEL_REGISTRY_TOKEN", "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return {
                "configured": True,
                "synced": True,
                "status": response.status,
                "response": raw[:2000],
            }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "configured": True,
            "synced": False,
            "error": str(exc),
        }


@router.get("/status")
def platform_status(
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    latest_telemetry = db.execute(
        select(Telemetry)
        .order_by(desc(Telemetry.timestamp), desc(Telemetry.id))
        .limit(1)
    ).scalar_one_or_none()

    manifest_path = Path(
        os.getenv(
            "FLEETMIND_ARCHIVE_MANIFEST",
            "/archive/manifest.json",
        )
    )

    counts = {
        "outcomes": db.scalar(
            select(func.count()).select_from(DiagnosticRecommendationOutcome)
        )
        or 0,
        "policies": db.scalar(
            select(func.count()).select_from(DiagnosticRecommendationPolicy)
        )
        or 0,
        "policyEvaluations": db.scalar(
            select(func.count()).select_from(DiagnosticPolicyEvaluation)
        )
        or 0,
        "shadowExperiments": db.scalar(
            select(func.count()).select_from(DiagnosticShadowExperiment)
        )
        or 0,
        "registeredModels": db.scalar(
            select(func.count()).select_from(DiagnosticModelRegistryEntry)
        )
        or 0,
        "assetTelemetryRows": db.scalar(
            select(func.count()).select_from(AssetTelemetryRecord)
        )
        or 0,
    }

    return {
        "phase": "9.x",
        "environment": os.getenv("FLEETMIND_ENV", "development"),
        "counts": counts,
        "latestTelemetryAt": (
            latest_telemetry.timestamp.isoformat()
            if latest_telemetry is not None
            else None
        ),
        "archive": {
            "manifestPath": str(manifest_path),
            "manifestPresent": manifest_path.exists(),
        },
        "capabilities": {
            "prometheusMetrics": True,
            "openTelemetry": os.getenv("OTEL_ENABLED", "false").lower()
            in ("1", "true", "yes", "on"),
            "loadHarness": True,
            "parquetArchive": True,
            "icebergAdapter": True,
            "helmDeployment": True,
            "modelRegistry": True,
            "driftMonitoring": True,
            "multiAssetPlugins": [row["assetType"] for row in plugin_catalog()],
        },
        "validationBoundary": {
            "implementationDelivered": True,
            "hundredKEventsPerSecondEmpiricallyVerified": False,
            "disasterRecoveryEmpiricallyVerified": False,
            "productionSLOsClaimedAchieved": False,
        },
    }


@router.get("/slo")
def slo_definitions() -> dict[str, Any]:
    return SLO_DEFINITIONS


class ModelRegisterRequest(BaseModel):
    modelName: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    lineage: str = Field(min_length=1, max_length=96)
    artifactUri: str = Field(min_length=1)
    artifactSha256: str = Field(min_length=32, max_length=64)
    featureSchemaSha256: str = Field(min_length=32, max_length=64)
    benchmarkSnapshotSha256: str | None = None
    benchmarkStatus: str | None = None
    sourceRunId: int | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    featureBaseline: dict[str, Any] | None = None
    actor: str = "operator"
    notes: str = ""
    syncExternal: bool = False


@router.post("/model-registry")
def register_model(
    request: ModelRegisterRequest,
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    existing = db.execute(
        select(DiagnosticModelRegistryEntry).where(
            DiagnosticModelRegistryEntry.model_name == request.modelName,
            DiagnosticModelRegistryEntry.version == request.version,
        )
    ).scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Model name/version is already registered",
        )

    baseline = request.featureBaseline
    if baseline is None:
        baseline = _feature_baseline(_latest_vehicle_telemetry(db))

    row = DiagnosticModelRegistryEntry(
        model_name=request.modelName,
        version=request.version,
        lineage=request.lineage,
        source_run_id=request.sourceRunId,
        stage="CANDIDATE",
        artifact_uri=request.artifactUri,
        artifact_sha256=request.artifactSha256,
        feature_schema_sha256=request.featureSchemaSha256,
        benchmark_snapshot_sha256=request.benchmarkSnapshotSha256,
        benchmark_status=request.benchmarkStatus,
        metrics_json=json.dumps(request.metrics, sort_keys=True),
        feature_baseline_json=json.dumps(baseline, sort_keys=True),
        created_at=_now(),
        created_by=request.actor.strip() or "operator",
        notes=request.notes,
    )

    sync_result = {"configured": False, "synced": False}
    if request.syncExternal:
        sync_result = _external_registry_sync(
            {
                "modelName": request.modelName,
                "version": request.version,
                "lineage": request.lineage,
                "artifactUri": request.artifactUri,
                "artifactSha256": request.artifactSha256,
                "featureSchemaSha256": request.featureSchemaSha256,
                "benchmarkSnapshotSha256": request.benchmarkSnapshotSha256,
                "benchmarkStatus": request.benchmarkStatus,
                "metrics": request.metrics,
            }
        )
        row.external_sync_json = json.dumps(sync_result, sort_keys=True)

    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Model registration conflicted with an existing version",
        )
    db.refresh(row)

    payload = _registry_payload(row)
    payload["externalSync"] = sync_result
    return payload


@router.get("/model-registry")
def list_models(
    stage: str | None = Query(default=None),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    statement = select(DiagnosticModelRegistryEntry)
    if stage:
        if stage not in MODEL_STAGES:
            raise HTTPException(status_code=400, detail="Unsupported model stage")
        statement = statement.where(DiagnosticModelRegistryEntry.stage == stage)

    rows = db.execute(
        statement.order_by(
            desc(DiagnosticModelRegistryEntry.created_at),
            desc(DiagnosticModelRegistryEntry.id),
        )
    ).scalars().all()
    return {
        "rulesVersion": MODEL_OPS_RULES_VERSION,
        "models": [_registry_payload(row) for row in rows],
    }


class ModelPromotionRequest(BaseModel):
    actor: str = "operator"
    expectedFeatureSchemaSha256: str | None = None
    syncExternal: bool = False


@router.post("/model-registry/{model_id}/promote")
def promote_model(
    model_id: int,
    request: ModelPromotionRequest,
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    row = db.get(DiagnosticModelRegistryEntry, model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Registered model not found")

    run = _latest_diagnostic_run(db)
    active_schema = request.expectedFeatureSchemaSha256
    if active_schema is None and run is not None:
        active_schema = run.feature_schema_sha256

    readiness = promotion_readiness(
        artifact_sha256=row.artifact_sha256,
        feature_schema_sha256=row.feature_schema_sha256,
        active_feature_schema_sha256=active_schema,
        benchmark_snapshot_sha256=row.benchmark_snapshot_sha256,
        benchmark_status=row.benchmark_status,
    )
    if not readiness["ready"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Model promotion gate failed",
                "readiness": readiness,
            },
        )

    current_production = db.execute(
        select(DiagnosticModelRegistryEntry).where(
            DiagnosticModelRegistryEntry.model_name == row.model_name,
            DiagnosticModelRegistryEntry.stage == "PRODUCTION",
            DiagnosticModelRegistryEntry.id != row.id,
        )
    ).scalars().all()
    for previous in current_production:
        previous.stage = "ARCHIVED"

    row.stage = "PRODUCTION"
    row.promoted_at = _now()
    row.promoted_by = request.actor.strip() or "operator"

    if request.syncExternal:
        row.external_sync_json = json.dumps(
            _external_registry_sync(_registry_payload(row)),
            sort_keys=True,
        )

    db.commit()
    payload = _registry_payload(row)
    payload["promotionReadiness"] = readiness
    payload["deploymentBoundary"] = (
        "Registry promotion records governance state only; deployment consumers "
        "must explicitly select the production registry entry."
    )
    return payload


@router.get("/model-registry/{model_id}/drift")
def model_drift(
    model_id: int,
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    row = db.get(DiagnosticModelRegistryEntry, model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Registered model not found")

    baseline = _json_object(row.feature_baseline_json)
    current = _feature_baseline(
        _latest_vehicle_telemetry(db),
        features=list(baseline.keys()),
    )
    report = drift_report(baseline, current)
    return {
        "model": _registry_payload(row),
        "currentFeatureStats": current,
        "drift": report,
    }


@router.get("/assets/plugins")
def asset_plugins() -> dict[str, Any]:
    return {
        "rulesVersion": ASSET_PLUGIN_RULES_VERSION,
        "plugins": plugin_catalog(),
        "claimBoundary": {
            "operationalAttentionOnly": True,
            "autonomousControl": False,
        },
    }


class AssetValidateRequest(BaseModel):
    event: dict[str, Any]


@router.post("/assets/validate")
def validate_asset_payload(
    request: AssetValidateRequest,
) -> dict[str, Any]:
    validation = validate_asset_event(request.event)
    result: dict[str, Any] = {"validation": validation}
    if validation["valid"]:
        result["score"] = score_asset_event(request.event)
    return result


@router.get("/assets/summary")
def asset_summary(
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    latest = (
        select(
            AssetTelemetryRecord.asset_id,
            func.max(AssetTelemetryRecord.id).label("max_id"),
        )
        .group_by(AssetTelemetryRecord.asset_id)
        .subquery()
    )
    rows = db.execute(
        select(AssetTelemetryRecord).join(
            latest,
            AssetTelemetryRecord.id == latest.c.max_id,
        )
    ).scalars().all()

    by_type: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = by_type.setdefault(
            row.asset_type,
            {"assets": 0, "healthy": 0, "degraded": 0, "critical": 0},
        )
        bucket["assets"] += 1
        bucket[row.status] = bucket.get(row.status, 0) + 1

    return {
        "rulesVersion": ASSET_PLUGIN_RULES_VERSION,
        "assetCount": len(rows),
        "byType": [
            {"assetType": asset_type, **counts}
            for asset_type, counts in sorted(by_type.items())
        ],
        "attentionRequired": sum(1 for row in rows if row.status != "healthy"),
        "claimBoundary": {
            "operationalAttentionOnly": True,
            "physicalFailureProbability": False,
        },
    }


@router.get("/assets/{asset_id}")
def asset_detail(
    asset_id: str,
    limit: int = Query(default=50, ge=1, le=250),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = db.execute(
        select(AssetTelemetryRecord)
        .where(AssetTelemetryRecord.asset_id == asset_id)
        .order_by(
            desc(AssetTelemetryRecord.timestamp),
            desc(AssetTelemetryRecord.id),
        )
        .limit(limit)
    ).scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="Asset not found")

    return {
        "assetId": asset_id,
        "assetType": rows[0].asset_type,
        "model": rows[0].model,
        "site": rows[0].site,
        "firmware": rows[0].firmware,
        "history": [
            {
                "eventId": row.event_id,
                "timestamp": row.timestamp.isoformat(),
                "experimentId": row.experiment_id,
                "attentionScore": round(float(row.attention_score), 4),
                "status": row.status,
                "metrics": _json_object(row.metrics_json),
                "evidence": _json_list(row.evidence_json),
            }
            for row in rows
        ],
        "claimBoundary": {
            "operationalAttentionOnly": True,
            "autonomousPhysicalAction": False,
        },
    }
