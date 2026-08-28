"""FleetMind Phases 8.2-8.5: outcome verification and policy learning."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleetmind_common.closed_loop_rules import (
    CLOSED_LOOP_RULES_VERSION,
    STATE_EXECUTED,
    recommendation_candidates,
    recommendation_key,
)
from fleetmind_common.db import SessionLocal
from fleetmind_common.diagnostic_store import (
    DiagnosticCase,
    DiagnosticFleetDecisionSnapshot,
    DiagnosticModelRun,
    DiagnosticOperationalRecommendation,
    DiagnosticPrediction,
    DiagnosticReplayPoint,
)
from fleetmind_common.effectiveness_rules import summarize_effectiveness
from fleetmind_common.models import Telemetry
from fleetmind_common.outcome_rules import (
    DEFAULT_MIN_OBSERVATION_MILES,
    DEFAULT_MIN_OBSERVATION_SECONDS,
    OUTCOME_RULES_VERSION,
    evaluate_observed_outcome,
    outcome_evaluation_key,
)
from fleetmind_common.platform_store import (
    DiagnosticPolicyEvaluation,
    DiagnosticRecommendationOutcome,
    DiagnosticRecommendationPolicy,
    DiagnosticShadowExperiment,
)
from fleetmind_common.policy_evaluation_rules import (
    DEFAULT_CANDIDATE_POLICY,
    DEFAULT_CONTROL_POLICY,
    POLICY_EVALUATION_RULES_VERSION,
    SHADOW_EXPERIMENT_RULES_VERSION,
    canonical_hash,
    compare_shadow_results,
    evaluate_policy,
    policy_evaluation_key,
)


router = APIRouter(
    prefix="/api/v1/diagnostics",
    tags=["closed-loop-learning"],
)


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


def _require_run(
    db: Session,
    run_id: int | None,
) -> tuple[str, DiagnosticModelRun]:
    if run_id is not None:
        run = db.get(DiagnosticModelRun, int(run_id))
        if run is None:
            raise HTTPException(status_code=404, detail="Diagnostic run not found")
        return run.experiment_id, run

    experiment_id = _active_experiment_id(db)
    if experiment_id is None:
        raise HTTPException(
            status_code=503,
            detail="No active tagged telemetry experiment is available",
        )

    run = db.execute(
        select(DiagnosticModelRun)
        .where(DiagnosticModelRun.experiment_id == experiment_id)
        .order_by(desc(DiagnosticModelRun.created_at), desc(DiagnosticModelRun.id))
        .limit(1)
    ).scalar_one_or_none()

    if run is None:
        raise HTTPException(
            status_code=503,
            detail="No diagnostic run is available for the active experiment",
        )
    return experiment_id, run


def _latest_telemetry(
    db: Session,
    *,
    experiment_id: str,
    vehicle_id: str,
    at_or_before: datetime | None = None,
    strictly_after: datetime | None = None,
) -> Telemetry | None:
    statement = select(Telemetry).where(
        Telemetry.experiment_id == experiment_id,
        Telemetry.vehicle_id == vehicle_id,
    )
    if at_or_before is not None:
        statement = statement.where(Telemetry.timestamp <= at_or_before)
    if strictly_after is not None:
        statement = statement.where(Telemetry.timestamp > strictly_after)

    return db.execute(
        statement.order_by(desc(Telemetry.timestamp), desc(Telemetry.id)).limit(1)
    ).scalar_one_or_none()


def _latest_replay(
    db: Session,
    *,
    run_id: int,
    vehicle_id: str,
    at_or_before: datetime | None = None,
    strictly_after: datetime | None = None,
) -> DiagnosticReplayPoint | None:
    statement = select(DiagnosticReplayPoint).where(
        DiagnosticReplayPoint.run_id == run_id,
        DiagnosticReplayPoint.vehicle_id == vehicle_id,
    )
    if at_or_before is not None:
        statement = statement.where(
            DiagnosticReplayPoint.anchor_timestamp <= at_or_before
        )
    if strictly_after is not None:
        statement = statement.where(
            DiagnosticReplayPoint.anchor_timestamp > strictly_after
        )

    return db.execute(
        statement.order_by(
            desc(DiagnosticReplayPoint.anchor_timestamp),
            desc(DiagnosticReplayPoint.id),
        ).limit(1)
    ).scalar_one_or_none()


def _current_prediction(
    db: Session,
    *,
    run_id: int,
    vehicle_id: str,
) -> DiagnosticPrediction | None:
    return db.execute(
        select(DiagnosticPrediction)
        .where(
            DiagnosticPrediction.run_id == run_id,
            DiagnosticPrediction.vehicle_id == vehicle_id,
        )
        .order_by(desc(DiagnosticPrediction.generated_at))
        .limit(1)
    ).scalar_one_or_none()


def _decision_record(
    db: Session,
    *,
    run_id: int,
    vehicle_id: str,
) -> dict[str, Any]:
    snapshot = db.execute(
        select(DiagnosticFleetDecisionSnapshot)
        .where(DiagnosticFleetDecisionSnapshot.run_id == run_id)
        .order_by(
            desc(DiagnosticFleetDecisionSnapshot.created_at),
            desc(DiagnosticFleetDecisionSnapshot.id),
        )
        .limit(1)
    ).scalar_one_or_none()

    if snapshot is None:
        return {}

    records = _json_list(snapshot.records_json)
    for record in records:
        if (
            isinstance(record, dict)
            and str(record.get("vehicleId") or "") == vehicle_id
        ):
            return record
    return {}


def _case_status(
    db: Session,
    case_id: int | None,
) -> str | None:
    if case_id is None:
        return None
    row = db.get(DiagnosticCase, int(case_id))
    return row.status if row is not None else None


def _telemetry_payload(row: Telemetry | None) -> dict[str, Any]:
    if row is None:
        return {}

    return {
        "timestamp": row.timestamp.isoformat(),
        "mileage": round(float(row.mileage), 3),
        "riskScore": round(float(row.risk_score), 6),
        "telemetryStatus": row.status,
        "context": {
            "model": row.model,
            "factory": row.factory,
            "firmware": row.firmware,
            "pumpRevision": row.pump_revision,
        },
        "telemetry": {
            "ambientTempC": round(float(row.ambient_temp_c), 4),
            "batteryTempC": round(float(row.battery_temp_c), 4),
            "coolantTempC": round(float(row.coolant_temp_c), 4),
            "pumpCurrentA": round(float(row.pump_current_a), 4),
            "pumpRPM": round(float(row.pump_rpm), 4),
        },
    }


def _diagnostic_payload(
    replay: DiagnosticReplayPoint | None,
    prediction: DiagnosticPrediction | None,
) -> dict[str, Any]:
    row = replay or prediction
    if row is None:
        return {}

    timestamp = (
        row.anchor_timestamp
        if hasattr(row, "anchor_timestamp")
        else row.generated_at
    )
    return {
        "diagnosticTimestamp": timestamp.isoformat(),
        "topClass": row.top_class,
        "topConfidence": round(float(row.top_confidence), 6),
    }


def _merge_snapshot(
    *,
    telemetry: Telemetry | None,
    replay: DiagnosticReplayPoint | None,
    prediction: DiagnosticPrediction | None,
    decision: dict[str, Any],
    case_status: str | None,
    source: dict[str, Any] | None,
) -> dict[str, Any]:
    source = source or {}
    result: dict[str, Any] = {}
    result.update(_telemetry_payload(telemetry))
    result.update(_diagnostic_payload(replay, prediction))

    if not result.get("topClass") and source.get("topClass"):
        result["topClass"] = source.get("topClass")
    if result.get("topConfidence") is None and source.get("topConfidence") is not None:
        result["topConfidence"] = source.get("topConfidence")

    attention = decision.get("attentionScore")
    if attention is None:
        attention = source.get("attentionScore")
    if attention is not None:
        result["attentionScore"] = float(attention)

    gaps = decision.get("coverageGaps")
    if not isinstance(gaps, list):
        gaps = source.get("coverageGaps")
    if isinstance(gaps, list):
        result["coverageGapCount"] = len(gaps)
        result["coverageGaps"] = list(gaps)

    if case_status:
        result["caseStatus"] = case_status
    elif source.get("caseStatus"):
        result["caseStatus"] = source.get("caseStatus")

    if not result.get("context"):
        context = {
            key: source.get(key)
            for key in ("model", "factory", "firmware", "pumpRevision")
            if source.get(key) is not None
        }
        if context:
            result["context"] = context

    result["sourceSnapshot"] = source
    return result


def _outcome_snapshots(
    db: Session,
    recommendation: DiagnosticOperationalRecommendation,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    executed_at = recommendation.executed_at
    source = _json_object(recommendation.source_snapshot_json)

    source_run = db.get(
        DiagnosticModelRun,
        recommendation.run_id,
    )
    post_run = source_run
    if source_run is not None:
        post_run = db.execute(
            select(DiagnosticModelRun)
            .where(
                DiagnosticModelRun.experiment_id
                == recommendation.experiment_id,
                DiagnosticModelRun.lineage
                == source_run.lineage,
            )
            .order_by(
                desc(DiagnosticModelRun.created_at),
                desc(DiagnosticModelRun.id),
            )
            .limit(1)
        ).scalar_one_or_none() or source_run

    post_run_id = (
        post_run.id
        if post_run is not None
        else recommendation.run_id
    )

    decision = _decision_record(
        db,
        run_id=post_run_id,
        vehicle_id=recommendation.vehicle_id,
    )

    baseline_telemetry = _latest_telemetry(
        db,
        experiment_id=recommendation.experiment_id,
        vehicle_id=recommendation.vehicle_id,
        at_or_before=executed_at,
    )
    baseline_replay = _latest_replay(
        db,
        run_id=recommendation.run_id,
        vehicle_id=recommendation.vehicle_id,
        at_or_before=executed_at,
    )

    baseline = _merge_snapshot(
        telemetry=baseline_telemetry,
        replay=baseline_replay,
        prediction=None,
        decision={},
        case_status=source.get("caseStatus"),
        source=source,
    )

    if executed_at is None:
        return baseline, None

    post_telemetry = _latest_telemetry(
        db,
        experiment_id=recommendation.experiment_id,
        vehicle_id=recommendation.vehicle_id,
        strictly_after=executed_at,
    )
    post_replay = _latest_replay(
        db,
        run_id=post_run_id,
        vehicle_id=recommendation.vehicle_id,
        strictly_after=executed_at,
    )
    current_prediction = _current_prediction(
        db,
        run_id=post_run_id,
        vehicle_id=recommendation.vehicle_id,
    )

    if post_telemetry is None and post_replay is None:
        return baseline, None

    post = _merge_snapshot(
        telemetry=post_telemetry,
        replay=post_replay,
        prediction=current_prediction,
        decision=decision,
        case_status=_case_status(db, recommendation.case_id),
        source={},
    )
    return baseline, post


def _snapshot_time(snapshot: dict[str, Any] | None) -> datetime | None:
    if not snapshot:
        return None
    for key in ("timestamp", "diagnosticTimestamp"):
        value = snapshot.get(key)
        if not isinstance(value, str):
            continue
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def _outcome_payload(row: DiagnosticRecommendationOutcome) -> dict[str, Any]:
    return {
        "id": row.id,
        "recommendationId": row.recommendation_id,
        "runId": row.run_id,
        "experimentId": row.experiment_id,
        "vehicleId": row.vehicle_id,
        "recommendationType": row.recommendation_type,
        "evaluationKey": row.evaluation_key,
        "evaluationVersion": row.evaluation_version,
        "status": row.status,
        "score": round(float(row.score), 4),
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
        "executedAt": row.executed_at.isoformat() if row.executed_at else None,
        "observationStartedAt": (
            row.observation_started_at.isoformat()
            if row.observation_started_at
            else None
        ),
        "observationCompletedAt": (
            row.observation_completed_at.isoformat()
            if row.observation_completed_at
            else None
        ),
        "baseline": _json_object(row.baseline_snapshot_json),
        "post": _json_object(row.post_snapshot_json),
        "factors": _json_list(row.factors_json),
        "context": _json_object(row.context_json),
        "materializedBy": row.materialized_by,
        "claimBoundary": {
            "observedChangeOnly": True,
            "physicalRepairConfirmed": False,
            "maintenanceCausalityEstablished": False,
        },
    }


class OutcomeEvaluateRequest(BaseModel):
    actor: str = "operator"
    recommendationIds: list[int] | None = None
    materialize: bool = False
    minObservationMiles: float = Field(
        default=DEFAULT_MIN_OBSERVATION_MILES,
        ge=0.0,
    )
    minObservationSeconds: float = Field(
        default=DEFAULT_MIN_OBSERVATION_SECONDS,
        ge=0.0,
    )


@router.post("/closed-loop/outcomes/evaluate")
def evaluate_outcomes(
    request: OutcomeEvaluateRequest,
    run_id: int | None = Query(default=None),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    experiment_id, run = _require_run(db, run_id)

    statement = select(DiagnosticOperationalRecommendation).where(
        DiagnosticOperationalRecommendation.run_id == run.id,
        DiagnosticOperationalRecommendation.status == STATE_EXECUTED,
    )
    if request.recommendationIds:
        statement = statement.where(
            DiagnosticOperationalRecommendation.id.in_(request.recommendationIds)
        )

    recommendations = db.execute(
        statement.order_by(
            DiagnosticOperationalRecommendation.executed_at,
            DiagnosticOperationalRecommendation.id,
        )
    ).scalars().all()

    previews = []
    created_count = 0
    updated_count = 0
    existing_count = 0
    actor = request.actor.strip() or "operator"

    for recommendation in recommendations:
        baseline, post = _outcome_snapshots(db, recommendation)
        result = evaluate_observed_outcome(
            baseline,
            post,
            min_observation_miles=request.minObservationMiles,
            min_observation_seconds=request.minObservationSeconds,
        )
        evaluation_key = outcome_evaluation_key(
            recommendation_id=recommendation.id,
        )

        preview = {
            "recommendationId": recommendation.id,
            "vehicleId": recommendation.vehicle_id,
            "recommendationType": recommendation.recommendation_type,
            "evaluationKey": evaluation_key,
            "evaluationVersion": OUTCOME_RULES_VERSION,
            "status": result["status"],
            "score": result["score"],
            "baseline": baseline,
            "post": post,
            "factors": result["factors"],
            "observation": result["observation"],
            "claimBoundary": result["claimBoundary"],
        }
        previews.append(preview)

        if not request.materialize:
            continue

        existing = db.execute(
            select(DiagnosticRecommendationOutcome).where(
                DiagnosticRecommendationOutcome.evaluation_key == evaluation_key
            )
        ).scalar_one_or_none()

        post_time = _snapshot_time(post)
        context = (
            (post or {}).get("context")
            or baseline.get("context")
            or {}
        )

        if existing is not None:
            existing.updated_at = _now()
            existing.executed_at = recommendation.executed_at
            existing.observation_started_at = recommendation.executed_at
            existing.observation_completed_at = post_time
            existing.status = result["status"]
            existing.score = float(result["score"])
            existing.baseline_snapshot_json = json.dumps(baseline, sort_keys=True)
            existing.post_snapshot_json = json.dumps(post or {}, sort_keys=True)
            existing.factors_json = json.dumps(result["factors"], sort_keys=True)
            existing.context_json = json.dumps(context, sort_keys=True)
            existing.materialized_by = actor
            updated_count += 1
            existing_count += 1
            continue

        row = DiagnosticRecommendationOutcome(
            recommendation_id=recommendation.id,
            run_id=recommendation.run_id,
            experiment_id=recommendation.experiment_id,
            vehicle_id=recommendation.vehicle_id,
            recommendation_type=recommendation.recommendation_type,
            evaluation_key=evaluation_key,
            evaluation_version=OUTCOME_RULES_VERSION,
            created_at=_now(),
            updated_at=_now(),
            executed_at=recommendation.executed_at,
            observation_started_at=recommendation.executed_at,
            observation_completed_at=post_time,
            status=result["status"],
            score=float(result["score"]),
            baseline_snapshot_json=json.dumps(baseline, sort_keys=True),
            post_snapshot_json=json.dumps(post or {}, sort_keys=True),
            factors_json=json.dumps(result["factors"], sort_keys=True),
            context_json=json.dumps(context, sort_keys=True),
            materialized_by=actor,
        )

        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            created_count += 1
        except IntegrityError:
            winner = db.execute(
                select(DiagnosticRecommendationOutcome).where(
                    DiagnosticRecommendationOutcome.evaluation_key
                    == evaluation_key
                )
            ).scalar_one_or_none()
            if winner is None:
                raise
            existing_count += 1

    if request.materialize:
        db.commit()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "evaluationVersion": OUTCOME_RULES_VERSION,
        "executedRecommendations": len(recommendations),
        "materializeRequested": request.materialize,
        "createdCount": created_count,
        "updatedCount": updated_count,
        "existingCount": existing_count,
        "outcomes": previews,
        "claimBoundary": {
            "observedChangeOnly": True,
            "physicalRepairConfirmed": False,
            "maintenanceCausalityEstablished": False,
        },
    }


@router.get("/closed-loop/outcomes/summary")
def outcome_summary(
    run_id: int | None = Query(default=None),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    experiment_id, run = _require_run(db, run_id)
    rows = db.execute(
        select(DiagnosticRecommendationOutcome).where(
            DiagnosticRecommendationOutcome.run_id == run.id
        )
    ).scalars().all()

    states = [
        "PENDING_OBSERVATION",
        "INSUFFICIENT_DATA",
        "IMPROVED",
        "STABLE",
        "WORSENED",
        "NO_MATERIAL_CHANGE",
    ]

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "evaluationVersion": OUTCOME_RULES_VERSION,
        "total": len(rows),
        "byStatus": [
            {
                "status": state,
                "count": sum(1 for row in rows if row.status == state),
            }
            for state in states
        ],
        "executedRecommendationsWithOutcome": len(
            {row.recommendation_id for row in rows}
        ),
        "claimBoundary": {
            "descriptiveObservationOnly": True,
            "causalSuccessRate": False,
        },
    }


@router.get("/closed-loop/outcomes")
def list_outcomes(
    run_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    vehicle_id: str | None = Query(default=None),
    recommendation_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    experiment_id, run = _require_run(db, run_id)
    statement = select(DiagnosticRecommendationOutcome).where(
        DiagnosticRecommendationOutcome.run_id == run.id
    )
    if status:
        statement = statement.where(
            DiagnosticRecommendationOutcome.status == status
        )
    if vehicle_id:
        statement = statement.where(
            DiagnosticRecommendationOutcome.vehicle_id == vehicle_id
        )
    if recommendation_id is not None:
        statement = statement.where(
            DiagnosticRecommendationOutcome.recommendation_id
            == recommendation_id
        )

    rows = db.execute(
        statement.order_by(
            desc(DiagnosticRecommendationOutcome.updated_at),
            desc(DiagnosticRecommendationOutcome.id),
        ).limit(limit)
    ).scalars().all()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "returned": len(rows),
        "outcomes": [_outcome_payload(row) for row in rows],
    }


@router.get("/closed-loop/outcomes/{outcome_id}")
def outcome_detail(
    outcome_id: int,
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    row = db.get(DiagnosticRecommendationOutcome, outcome_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Outcome not found")
    return _outcome_payload(row)


def _recommendation_analytics_payload(
    row: DiagnosticOperationalRecommendation,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "vehicleId": row.vehicle_id,
        "recommendationType": row.recommendation_type,
        "status": row.status,
        "createdAt": row.created_at,
        "assignedAt": row.assigned_at,
        "acknowledgedAt": row.acknowledged_at,
        "approvalRequiredAt": row.approval_required_at,
        "approvedAt": row.approved_at,
        "executionReadyAt": row.execution_ready_at,
        "executedAt": row.executed_at,
    }


def _outcome_analytics_payload(
    row: DiagnosticRecommendationOutcome,
) -> dict[str, Any]:
    return {
        "recommendationId": row.recommendation_id,
        "recommendationType": row.recommendation_type,
        "status": row.status,
        "score": float(row.score),
        "observationCompletedAt": row.observation_completed_at,
        "baseline": _json_object(row.baseline_snapshot_json),
        "post": _json_object(row.post_snapshot_json),
        "context": _json_object(row.context_json),
    }


@router.get("/closed-loop/effectiveness")
def closed_loop_effectiveness(
    run_id: int | None = Query(default=None),
    cohort_dimension: str = Query(
        default="recommendationType",
        pattern="^(recommendationType|factory|model|firmware|pumpRevision)$",
    ),
    min_group_outcomes: int = Query(default=5, ge=1, le=100),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    experiment_id, run = _require_run(db, run_id)

    recommendations = db.execute(
        select(DiagnosticOperationalRecommendation).where(
            DiagnosticOperationalRecommendation.run_id == run.id
        )
    ).scalars().all()
    outcomes = db.execute(
        select(DiagnosticRecommendationOutcome).where(
            DiagnosticRecommendationOutcome.run_id == run.id
        )
    ).scalars().all()

    payload = summarize_effectiveness(
        [_outcome_analytics_payload(row) for row in outcomes],
        [_recommendation_analytics_payload(row) for row in recommendations],
        cohort_dimension=cohort_dimension,
        min_group_outcomes=min_group_outcomes,
    )
    payload["runId"] = run.id
    payload["experimentId"] = experiment_id
    return payload


def _policy_payload(row: DiagnosticRecommendationPolicy) -> dict[str, Any]:
    return {
        "id": row.id,
        "policyKey": row.policy_key,
        "version": row.version,
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "rules": _json_object(row.rules_json),
        "createdAt": row.created_at.isoformat(),
        "updatedAt": row.updated_at.isoformat(),
        "createdBy": row.created_by,
        "promotedAt": row.promoted_at.isoformat() if row.promoted_at else None,
        "promotedBy": row.promoted_by,
        "disabledAt": row.disabled_at.isoformat() if row.disabled_at else None,
        "disabledBy": row.disabled_by,
        "rollbackOfId": row.rollback_of_id,
        "productionBehaviorChanged": False,
    }


def _upsert_default_policy(
    db: Session,
    definition: dict[str, Any],
    actor: str,
) -> tuple[DiagnosticRecommendationPolicy, bool]:
    row = db.execute(
        select(DiagnosticRecommendationPolicy).where(
            DiagnosticRecommendationPolicy.policy_key
            == definition["policyKey"],
            DiagnosticRecommendationPolicy.version
            == definition["version"],
        )
    ).scalar_one_or_none()
    if row is not None:
        return row, False

    row = DiagnosticRecommendationPolicy(
        policy_key=definition["policyKey"],
        version=definition["version"],
        name=definition["name"],
        description=definition["description"],
        status="CANDIDATE",
        rules_json=json.dumps(definition["rules"], sort_keys=True),
        created_at=_now(),
        updated_at=_now(),
        created_by=actor,
    )
    db.add(row)
    db.flush()
    return row, True


@router.post("/closed-loop/policies/bootstrap")
def bootstrap_policies(
    actor: str = Query(default="operator"),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    actor = actor.strip() or "operator"
    rows = []
    created = 0
    for definition in (DEFAULT_CONTROL_POLICY, DEFAULT_CANDIDATE_POLICY):
        row, was_created = _upsert_default_policy(db, definition, actor)
        rows.append(row)
        created += int(was_created)
    db.commit()
    return {
        "created": created,
        "policies": [_policy_payload(row) for row in rows],
    }


class PolicyCreateRequest(BaseModel):
    policyKey: str = Field(min_length=1, max_length=96)
    version: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    rules: dict[str, Any] = Field(default_factory=dict)
    actor: str = "operator"


@router.post("/closed-loop/policies")
def create_policy(
    request: PolicyCreateRequest,
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    existing = db.execute(
        select(DiagnosticRecommendationPolicy).where(
            DiagnosticRecommendationPolicy.policy_key == request.policyKey,
            DiagnosticRecommendationPolicy.version == request.version,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Policy key/version already exists",
        )

    row = DiagnosticRecommendationPolicy(
        policy_key=request.policyKey,
        version=request.version,
        name=request.name,
        description=request.description,
        status="DRAFT",
        rules_json=json.dumps(request.rules, sort_keys=True),
        created_at=_now(),
        updated_at=_now(),
        created_by=request.actor.strip() or "operator",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _policy_payload(row)


@router.get("/closed-loop/policies")
def list_policies(
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = db.execute(
        select(DiagnosticRecommendationPolicy).order_by(
            desc(DiagnosticRecommendationPolicy.updated_at),
            desc(DiagnosticRecommendationPolicy.id),
        )
    ).scalars().all()
    return {
        "rulesVersion": POLICY_EVALUATION_RULES_VERSION,
        "policies": [_policy_payload(row) for row in rows],
    }


def _frozen_policy_records(
    db: Session,
    run: DiagnosticModelRun,
) -> tuple[list[dict[str, Any]], str, bool, str]:
    snapshot = db.execute(
        select(DiagnosticFleetDecisionSnapshot)
        .where(DiagnosticFleetDecisionSnapshot.run_id == run.id)
        .order_by(
            desc(DiagnosticFleetDecisionSnapshot.created_at),
            desc(DiagnosticFleetDecisionSnapshot.id),
        )
        .limit(1)
    ).scalar_one_or_none()

    if snapshot is not None:
        records = [
            row
            for row in _json_list(snapshot.records_json)
            if isinstance(row, dict) and row.get("vehicleId")
        ]
        if records:
            input_hash = snapshot.state_hash or canonical_hash(records)
            return records, input_hash, True, "fleet_decision_snapshot"

    recommendations = db.execute(
        select(DiagnosticOperationalRecommendation)
        .where(DiagnosticOperationalRecommendation.run_id == run.id)
        .order_by(DiagnosticOperationalRecommendation.id)
    ).scalars().all()

    by_vehicle: dict[str, dict[str, Any]] = {}
    for row in recommendations:
        source = _json_object(row.source_snapshot_json)
        if source and source.get("vehicleId"):
            by_vehicle.setdefault(str(source["vehicleId"]), source)

    records = list(by_vehicle.values())
    return (
        records,
        canonical_hash(records),
        False,
        "recommendation_source_snapshots",
    )


def _policy_candidates(
    *,
    run: DiagnosticModelRun,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = []
    for record in records:
        try:
            rows = recommendation_candidates(record)
        except (ValueError, TypeError):
            continue

        context = {
            key: record.get(key)
            for key in (
                "factory",
                "model",
                "firmware",
                "pumpRevision",
                "hypothesisClass",
            )
            if record.get(key) is not None
        }

        for candidate in rows:
            enriched = dict(candidate)
            enriched["recommendationKey"] = recommendation_key(
                run_id=run.id,
                experiment_id=run.experiment_id,
                vehicle_id=str(candidate["vehicleId"]),
                recommendation_type=str(candidate["recommendationType"]),
                case_id=candidate.get("caseId"),
                source_key=str(candidate.get("sourceKey") or ""),
            )
            enriched["context"] = context
            candidates.append(enriched)
    return candidates


class PolicyEvaluateRequest(BaseModel):
    actor: str = "operator"
    persist: bool = True


@router.post("/closed-loop/policies/{policy_id}/evaluate")
def evaluate_recommendation_policy(
    policy_id: int,
    request: PolicyEvaluateRequest,
    run_id: int | None = Query(default=None),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    experiment_id, run = _require_run(db, run_id)
    policy = db.get(DiagnosticRecommendationPolicy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    records, input_hash, frozen, input_source = _frozen_policy_records(db, run)
    candidates = _policy_candidates(run=run, records=records)
    result = evaluate_policy(
        candidates,
        _json_object(policy.rules_json),
        input_is_frozen=frozen,
    )
    result["inputVehicles"] = len(records)
    result["inputSource"] = input_source
    result["inputHash"] = input_hash

    persisted_id = None
    if request.persist:
        key = policy_evaluation_key(
            policy_id=policy.id,
            run_id=run.id,
            input_hash=input_hash,
        )
        existing = db.execute(
            select(DiagnosticPolicyEvaluation).where(
                DiagnosticPolicyEvaluation.evaluation_key == key
            )
        ).scalar_one_or_none()

        if existing is None:
            row = DiagnosticPolicyEvaluation(
                policy_id=policy.id,
                run_id=run.id,
                experiment_id=experiment_id,
                evaluation_key=key,
                rules_version=POLICY_EVALUATION_RULES_VERSION,
                created_at=_now(),
                created_by=request.actor.strip() or "operator",
                input_hash=input_hash,
                input_source=input_source,
                input_is_frozen=frozen,
                candidate_count=int(result["selectedCandidates"]),
                duplicate_suppressed=int(result["duplicateSuppressed"]),
                conflict_count=len(result["conflicts"]),
                summary_json=json.dumps(
                    {k: v for k, v in result.items() if k != "candidates"},
                    sort_keys=True,
                ),
                candidates_json=json.dumps(result["candidates"], sort_keys=True),
            )
            try:
                with db.begin_nested():
                    db.add(row)
                    db.flush()
                persisted_id = row.id
            except IntegrityError:
                existing = db.execute(
                    select(DiagnosticPolicyEvaluation).where(
                        DiagnosticPolicyEvaluation.evaluation_key == key
                    )
                ).scalar_one_or_none()
                persisted_id = existing.id if existing else None
        else:
            persisted_id = existing.id
        db.commit()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "policy": _policy_payload(policy),
        "persistedEvaluationId": persisted_id,
        "evaluation": result,
    }


@router.get("/closed-loop/policy-evaluations")
def list_policy_evaluations(
    run_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    _, run = _require_run(db, run_id)
    rows = db.execute(
        select(DiagnosticPolicyEvaluation)
        .where(DiagnosticPolicyEvaluation.run_id == run.id)
        .order_by(
            desc(DiagnosticPolicyEvaluation.created_at),
            desc(DiagnosticPolicyEvaluation.id),
        )
        .limit(limit)
    ).scalars().all()

    return {
        "runId": run.id,
        "evaluations": [
            {
                "id": row.id,
                "policyId": row.policy_id,
                "evaluationKey": row.evaluation_key,
                "createdAt": row.created_at.isoformat(),
                "inputHash": row.input_hash,
                "inputSource": row.input_source,
                "inputIsFrozen": row.input_is_frozen,
                "candidateCount": row.candidate_count,
                "duplicateSuppressed": row.duplicate_suppressed,
                "conflictCount": row.conflict_count,
                "summary": _json_object(row.summary_json),
            }
            for row in rows
        ],
    }


def _latest_policy_evaluation(
    db: Session,
    policy_id: int,
) -> DiagnosticPolicyEvaluation | None:
    return db.execute(
        select(DiagnosticPolicyEvaluation)
        .where(DiagnosticPolicyEvaluation.policy_id == policy_id)
        .order_by(
            desc(DiagnosticPolicyEvaluation.created_at),
            desc(DiagnosticPolicyEvaluation.id),
        )
        .limit(1)
    ).scalar_one_or_none()


class PolicyActionRequest(BaseModel):
    actor: str = "operator"
    note: str | None = None


@router.post("/closed-loop/policies/{policy_id}/promote")
def promote_policy(
    policy_id: int,
    request: PolicyActionRequest,
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    policy = db.get(DiagnosticRecommendationPolicy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    evaluation = _latest_policy_evaluation(db, policy_id)
    if evaluation is None:
        raise HTTPException(
            status_code=409,
            detail="Policy must be evaluated before promotion",
        )

    summary = _json_object(evaluation.summary_json)
    promotion = summary.get("promotionCriteria") or {}
    if not promotion.get("met"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Policy promotion criteria are not met",
                "reasons": promotion.get("reasons") or [],
            },
        )

    actor = request.actor.strip() or "operator"
    promoted = db.execute(
        select(DiagnosticRecommendationPolicy).where(
            DiagnosticRecommendationPolicy.status == "PROMOTED",
            DiagnosticRecommendationPolicy.id != policy.id,
        )
    ).scalars().all()
    for row in promoted:
        row.status = "CANDIDATE"
        row.updated_at = _now()

    policy.status = "PROMOTED"
    policy.promoted_at = _now()
    policy.promoted_by = actor
    policy.updated_at = _now()
    db.commit()

    payload = _policy_payload(policy)
    payload["controlPlaneOnly"] = True
    payload["message"] = (
        "Promotion records policy governance metadata only. Existing live "
        "recommendation generation is unchanged until a separately reviewed "
        "production integration explicitly adopts the policy."
    )
    return payload


@router.post("/closed-loop/policies/{policy_id}/disable")
def disable_policy(
    policy_id: int,
    request: PolicyActionRequest,
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    policy = db.get(DiagnosticRecommendationPolicy, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")

    actor = request.actor.strip() or "operator"
    policy.status = "DISABLED"
    policy.disabled_at = _now()
    policy.disabled_by = actor
    policy.updated_at = _now()
    db.commit()
    return _policy_payload(policy)


class PolicyRollbackRequest(BaseModel):
    targetPolicyId: int
    actor: str = "operator"


@router.post("/closed-loop/policies/rollback")
def rollback_policy(
    request: PolicyRollbackRequest,
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    target = db.get(DiagnosticRecommendationPolicy, request.targetPolicyId)
    if target is None:
        raise HTTPException(status_code=404, detail="Rollback target not found")

    actor = request.actor.strip() or "operator"
    current = db.execute(
        select(DiagnosticRecommendationPolicy).where(
            DiagnosticRecommendationPolicy.status == "PROMOTED"
        )
    ).scalars().all()

    previous_ids = []
    for row in current:
        previous_ids.append(row.id)
        row.status = "DISABLED"
        row.disabled_at = _now()
        row.disabled_by = actor
        row.updated_at = _now()

    target.status = "PROMOTED"
    target.promoted_at = _now()
    target.promoted_by = actor
    target.updated_at = _now()
    target.rollback_of_id = previous_ids[0] if previous_ids else None
    db.commit()

    return {
        "target": _policy_payload(target),
        "disabledPolicyIds": previous_ids,
        "controlPlaneOnly": True,
        "productionBehaviorChanged": False,
    }


def _outcome_context_by_type(
    db: Session,
    run_id: int,
) -> dict[str, dict[str, int]]:
    rows = db.execute(
        select(DiagnosticRecommendationOutcome).where(
            DiagnosticRecommendationOutcome.run_id == run_id
        )
    ).scalars().all()

    result: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = result.setdefault(row.recommendation_type, {})
        bucket[row.status] = bucket.get(row.status, 0) + 1
    return result


class ShadowExperimentRequest(BaseModel):
    controlPolicyId: int
    candidatePolicyId: int
    actor: str = "operator"
    persist: bool = True


@router.post("/closed-loop/shadow-experiments")
def create_shadow_experiment(
    request: ShadowExperimentRequest,
    run_id: int | None = Query(default=None),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    experiment_id, run = _require_run(db, run_id)
    control = db.get(DiagnosticRecommendationPolicy, request.controlPolicyId)
    candidate = db.get(DiagnosticRecommendationPolicy, request.candidatePolicyId)
    if control is None or candidate is None:
        raise HTTPException(status_code=404, detail="Control or candidate policy not found")

    records, input_hash, frozen, input_source = _frozen_policy_records(db, run)
    raw_candidates = _policy_candidates(run=run, records=records)

    control_result = evaluate_policy(
        raw_candidates,
        _json_object(control.rules_json),
        input_is_frozen=frozen,
    )
    candidate_result = evaluate_policy(
        raw_candidates,
        _json_object(candidate.rules_json),
        input_is_frozen=frozen,
    )

    comparison = compare_shadow_results(
        control_result,
        candidate_result,
        outcome_summary_by_type=_outcome_context_by_type(db, run.id),
    )

    experiment_key = canonical_hash(
        {
            "runId": run.id,
            "controlPolicyId": control.id,
            "candidatePolicyId": candidate.id,
            "inputHash": input_hash,
            "rulesVersion": SHADOW_EXPERIMENT_RULES_VERSION,
        }
    )

    persisted_id = None
    if request.persist:
        existing = db.execute(
            select(DiagnosticShadowExperiment).where(
                DiagnosticShadowExperiment.experiment_key == experiment_key
            )
        ).scalar_one_or_none()

        if existing is None:
            row = DiagnosticShadowExperiment(
                experiment_key=experiment_key,
                run_id=run.id,
                experiment_id=experiment_id,
                control_policy_id=control.id,
                candidate_policy_id=candidate.id,
                status="COMPLETED",
                created_at=_now(),
                updated_at=_now(),
                actor=request.actor.strip() or "operator",
                input_hash=input_hash,
                input_source=input_source,
                input_is_frozen=frozen,
                frozen_input_json=json.dumps(records, sort_keys=True),
                control_result_json=json.dumps(control_result, sort_keys=True),
                candidate_result_json=json.dumps(candidate_result, sort_keys=True),
                comparison_json=json.dumps(comparison, sort_keys=True),
            )
            try:
                with db.begin_nested():
                    db.add(row)
                    db.flush()
                persisted_id = row.id
            except IntegrityError:
                existing = db.execute(
                    select(DiagnosticShadowExperiment).where(
                        DiagnosticShadowExperiment.experiment_key
                        == experiment_key
                    )
                ).scalar_one_or_none()
                persisted_id = existing.id if existing else None
        else:
            persisted_id = existing.id
        db.commit()

    return {
        "runId": run.id,
        "experimentId": experiment_id,
        "experimentKey": experiment_key,
        "persistedExperimentId": persisted_id,
        "inputSource": input_source,
        "inputIsFrozen": frozen,
        "inputVehicles": len(records),
        "controlPolicy": _policy_payload(control),
        "candidatePolicy": _policy_payload(candidate),
        "control": control_result,
        "candidate": candidate_result,
        "comparison": comparison,
    }


@router.get("/closed-loop/shadow-experiments")
def list_shadow_experiments(
    run_id: int | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    _, run = _require_run(db, run_id)
    rows = db.execute(
        select(DiagnosticShadowExperiment)
        .where(DiagnosticShadowExperiment.run_id == run.id)
        .order_by(
            desc(DiagnosticShadowExperiment.created_at),
            desc(DiagnosticShadowExperiment.id),
        )
        .limit(limit)
    ).scalars().all()

    return {
        "runId": run.id,
        "experiments": [
            {
                "id": row.id,
                "experimentKey": row.experiment_key,
                "controlPolicyId": row.control_policy_id,
                "candidatePolicyId": row.candidate_policy_id,
                "status": row.status,
                "createdAt": row.created_at.isoformat(),
                "actor": row.actor,
                "inputHash": row.input_hash,
                "inputSource": row.input_source,
                "inputIsFrozen": row.input_is_frozen,
                "comparison": _json_object(row.comparison_json),
                "claimBoundary": {
                    "shadowOnly": True,
                    "recommendationWrites": False,
                    "automaticPromotion": False,
                },
            }
            for row in rows
        ],
    }
