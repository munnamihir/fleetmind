from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sqlalchemy import func, select

from fleetmind_common.db import Base, SessionLocal, engine
from fleetmind_common.diagnostic_evidence import observable_evidence
from fleetmind_common.diagnostic_store import (
    DiagnosticModelRun,
    DiagnosticReplayPoint,
)
from app.diagnostic_models import predict_ranked_hypotheses
from app.diagnostic_run import (
    load_current_scoring_telemetry,
    replay_scoring_examples,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate observable-only diagnostic replay history for an "
            "existing persisted diagnostic model run."
        )
    )
    parser.add_argument(
        "--run-id",
        type=int,
        required=True,
        help=(
            "Persisted diagnostic_model_runs.id to backfill. "
            "The run's own experiment_id is authoritative."
        ),
    )
    return parser.parse_args()


def _bundle_model(bundle: dict, champion: str):
    mapping = {
        "transparent_baseline": "transparentBaseline",
        "multinomial_logistic": "multinomialLogistic",
        "xgboost_multiclass": "xgboostMulticlass",
    }
    key = mapping.get(champion)
    if key is None:
        raise ValueError(f"Unsupported diagnostic champion: {champion}")
    model = bundle.get(key)
    if model is None:
        raise ValueError(
            f"Model bundle does not contain champion model {key}"
        )
    return model


def backfill_run(run_id: int) -> dict:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        run = db.get(DiagnosticModelRun, run_id)
        if run is None:
            return {
                "status": "not_found",
                "runId": run_id,
                "reason": "diagnostic run does not exist",
            }

        if run.status != "trained" or not run.champion:
            return {
                "status": "waiting",
                "runId": run.id,
                "experimentId": run.experiment_id,
                "reason": "diagnostic run is not a trained champion run",
            }

        existing = int(
            db.scalar(
                select(func.count(DiagnosticReplayPoint.id)).where(
                    DiagnosticReplayPoint.run_id == run.id
                )
            )
            or 0
        )

        if existing > 0:
            vehicles = int(
                db.scalar(
                    select(
                        func.count(
                            func.distinct(
                                DiagnosticReplayPoint.vehicle_id
                            )
                        )
                    ).where(
                        DiagnosticReplayPoint.run_id == run.id
                    )
                )
                or 0
            )
            return {
                "status": "already_populated",
                "runId": run.id,
                "experimentId": run.experiment_id,
                "lineage": run.lineage,
                "champion": run.champion,
                "replayPoints": existing,
                "vehicles": vehicles,
            }

        experiment_id = run.experiment_id
        champion = run.champion
        lineage = run.lineage
        bundle_path = run.bundle_path
        feature_schema_sha256 = run.feature_schema_sha256

    if not bundle_path:
        return {
            "status": "error",
            "runId": run_id,
            "experimentId": experiment_id,
            "reason": "diagnostic run has no saved model bundle path",
        }

    path = Path(bundle_path)
    if not path.exists():
        return {
            "status": "error",
            "runId": run_id,
            "experimentId": experiment_id,
            "reason": f"model bundle not found: {bundle_path}",
        }

    bundle = joblib.load(path)

    if str(bundle.get("experimentId")) != experiment_id:
        raise ValueError(
            "Model bundle experiment does not match persisted diagnostic run"
        )

    if str(bundle.get("lineage")) != lineage:
        raise ValueError(
            "Model bundle lineage does not match persisted diagnostic run"
        )

    bundle_schema = bundle.get("featureSchemaSha256")
    if (
        feature_schema_sha256
        and bundle_schema
        and str(bundle_schema) != str(feature_schema_sha256)
    ):
        raise ValueError(
            "Model bundle feature schema does not match persisted run"
        )

    feature_names = tuple(bundle.get("featureNames") or ())
    if not feature_names:
        raise ValueError("Model bundle is missing featureNames")

    bundle_champion = str(bundle.get("champion") or "")
    if bundle_champion != champion:
        raise ValueError(
            "Model bundle champion does not match persisted diagnostic run"
        )

    model = _bundle_model(bundle, champion)

    # IMPORTANT: this reads telemetry for the persisted run's own experiment,
    # not whichever simulator experiment happens to be active now.
    with SessionLocal() as db:
        scoring_by_vehicle = load_current_scoring_telemetry(
            db,
            experiment_id,
        )

    examples = replay_scoring_examples(
        scoring_by_vehicle,
        experiment_id=experiment_id,
    )

    if not examples:
        return {
            "status": "waiting",
            "runId": run_id,
            "experimentId": experiment_id,
            "reason": (
                "no eligible observable replay windows are available "
                "for the persisted run experiment"
            ),
        }

    ranked = predict_ranked_hypotheses(
        model,
        examples,
        feature_names=feature_names,
        top_k=3,
    )

    generated_at = datetime.now(timezone.utc)

    rows = []
    for example, hypotheses in zip(examples, ranked):
        top = hypotheses[0]
        rows.append(
            DiagnosticReplayPoint(
                run_id=run_id,
                generated_at=generated_at,
                experiment_id=experiment_id,
                vehicle_id=example.vehicle_id,
                anchor_timestamp=example.anchor_timestamp,
                anchor_mileage=example.anchor_mileage,
                top_class=str(top["class"]),
                top_confidence=float(top["confidence"]),
                hypotheses_json=json.dumps(
                    hypotheses,
                    sort_keys=True,
                ),
                evidence_json=json.dumps(
                    observable_evidence(
                        str(top["class"]),
                        example.features,
                    ),
                    sort_keys=True,
                ),
            )
        )

    # Fail closed if another process populated the run after our initial read.
    with SessionLocal() as db:
        existing_now = int(
            db.scalar(
                select(func.count(DiagnosticReplayPoint.id)).where(
                    DiagnosticReplayPoint.run_id == run_id
                )
            )
            or 0
        )
        if existing_now > 0:
            return {
                "status": "already_populated",
                "runId": run_id,
                "experimentId": experiment_id,
                "lineage": lineage,
                "champion": champion,
                "replayPoints": existing_now,
            }

        db.add_all(rows)
        db.commit()

    vehicles = len({row.vehicle_id for row in rows})

    return {
        "status": "populated",
        "runId": run_id,
        "experimentId": experiment_id,
        "lineage": lineage,
        "champion": champion,
        "replayPoints": len(rows),
        "vehicles": vehicles,
        "policy": {
            "currentRunOnly": True,
            "exactExperimentOnly": True,
            "sameLineageOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
            "runPinned": True,
        },
    }


def main() -> None:
    args = _parse_args()
    print(
        json.dumps(
            backfill_run(args.run_id),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
