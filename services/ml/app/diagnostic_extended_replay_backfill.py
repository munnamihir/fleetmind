from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import joblib
from sqlalchemy import delete, func, select, text

from fleetmind_common.db import Base, SessionLocal, engine
from fleetmind_common.diagnostic_dataset import DiagnosticExample
from fleetmind_common.diagnostic_evidence import observable_evidence
from fleetmind_common.diagnostic_store import (
    DiagnosticModelRun,
    DiagnosticPrediction,
    DiagnosticReplayPoint,
)
from fleetmind_common.diagnostics import (
    DiagnosticTelemetryPoint,
    extract_diagnostic_features,
)
from app.diagnostic_models import predict_ranked_hypotheses
from app.diagnostic_run import WINDOW_SIZE


EXTENDED_ROWS_PER_VEHICLE = 600
EXTENDED_MAX_POINTS_PER_VEHICLE = 64


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replace a trained diagnostic run's short replay with a longer, "
            "run-frozen, observable-only history."
        )
    )
    parser.add_argument(
        "--run-id",
        type=int,
        required=True,
        help="Persisted trained diagnostic_model_runs.id.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help=(
            "Required when replay rows already exist. Replacement is scoped "
            "only to the explicit run id."
        ),
    )
    parser.add_argument(
        "--rows-per-vehicle",
        type=int,
        default=EXTENDED_ROWS_PER_VEHICLE,
    )
    parser.add_argument(
        "--max-points-per-vehicle",
        type=int,
        default=EXTENDED_MAX_POINTS_PER_VEHICLE,
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


def _telemetry_points(rows) -> Dict[str, List[DiagnosticTelemetryPoint]]:
    by_vehicle: Dict[str, List[DiagnosticTelemetryPoint]] = defaultdict(list)

    for row in rows:
        point = DiagnosticTelemetryPoint(
            timestamp=row["timestamp"],
            vehicle_id=row["vehicle_id"],
            experiment_id=row["experiment_id"],
            mileage=float(row["mileage"]),
            ambient_temp_c=float(row["ambient_temp_c"]),
            speed_mph=float(row["speed_mph"]),
            soc_pct=float(row["soc_pct"]),
            pack_voltage_v=float(row["pack_voltage_v"]),
            pack_current_a=float(row["pack_current_a"]),
            battery_temp_c=float(row["battery_temp_c"]),
            cell_imbalance_v=float(row["cell_imbalance_v"]),
            motor_temp_c=float(row["motor_temp_c"]),
            inverter_temp_c=float(row["inverter_temp_c"]),
            motor_rpm=float(row["motor_rpm"]),
            coolant_temp_c=float(row["coolant_temp_c"]),
            pump_rpm=float(row["pump_rpm"]),
            pump_current_a=float(row["pump_current_a"]),
        )
        by_vehicle[point.vehicle_id].append(point)

    return by_vehicle


def load_run_frozen_history(
    db,
    *,
    run_id: int,
    experiment_id: str,
    rows_per_vehicle: int,
) -> Dict[str, List[DiagnosticTelemetryPoint]]:
    """
    Load observable telemetry only up to each persisted run prediction anchor.

    The persisted DiagnosticPrediction anchor freezes the upper bound. Telemetry
    generated after the run is deliberately excluded.
    """

    rows = db.execute(
        text(
            """
            WITH run_cutoffs AS (
                SELECT
                    vehicle_id,
                    anchor_timestamp
                FROM diagnostic_predictions
                WHERE run_id = :run_id
            ),
            ranked AS (
                SELECT
                    t.id,
                    t.timestamp,
                    t.vehicle_id,
                    t.experiment_id,
                    t.mileage,
                    t.ambient_temp_c,
                    t.speed_mph,
                    t.soc_pct,
                    t.pack_voltage_v,
                    t.pack_current_a,
                    t.battery_temp_c,
                    t.cell_imbalance_v,
                    t.motor_temp_c,
                    t.inverter_temp_c,
                    t.motor_rpm,
                    t.coolant_temp_c,
                    t.pump_rpm,
                    t.pump_current_a,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.vehicle_id
                        ORDER BY t.id DESC
                    ) AS vehicle_row_number
                FROM telemetry t
                INNER JOIN run_cutoffs c
                    ON c.vehicle_id = t.vehicle_id
                WHERE t.experiment_id = :experiment_id
                  AND t.timestamp <= c.anchor_timestamp
            )
            SELECT
                id,
                timestamp,
                vehicle_id,
                experiment_id,
                mileage,
                ambient_temp_c,
                speed_mph,
                soc_pct,
                pack_voltage_v,
                pack_current_a,
                battery_temp_c,
                cell_imbalance_v,
                motor_temp_c,
                inverter_temp_c,
                motor_rpm,
                coolant_temp_c,
                pump_rpm,
                pump_current_a
            FROM ranked
            WHERE vehicle_row_number <= :rows_per_vehicle
            ORDER BY vehicle_id, timestamp, id
            """
        ),
        {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "rows_per_vehicle": rows_per_vehicle,
        },
    ).mappings().all()

    return _telemetry_points(rows)


def _evenly_spaced_anchor_indexes(
    point_count: int,
    *,
    window_size: int,
    max_points: int,
) -> list[int]:
    first = window_size - 1
    last = point_count - 1

    if point_count < window_size or max_points < 1:
        return []

    eligible = last - first + 1
    if eligible <= max_points:
        return list(range(first, last + 1))

    if max_points == 1:
        return [last]

    span = last - first
    indexes = [
        int(round(first + (span * position / (max_points - 1))))
        for position in range(max_points)
    ]
    deduped = list(dict.fromkeys(indexes))

    if deduped[0] != first:
        deduped.insert(0, first)
    if deduped[-1] != last:
        deduped.append(last)

    if len(deduped) > max_points:
        deduped = deduped[: max_points - 1] + [last]

    return deduped


def extended_replay_examples(
    telemetry_by_vehicle: Dict[str, List[DiagnosticTelemetryPoint]],
    *,
    experiment_id: str,
    max_points_per_vehicle: int,
) -> list[DiagnosticExample]:
    examples: list[DiagnosticExample] = []

    for vehicle_id, raw_points in sorted(telemetry_by_vehicle.items()):
        points = sorted(
            [
                point
                for point in raw_points
                if point.experiment_id == experiment_id
            ],
            key=lambda point: point.timestamp,
        )

        anchor_indexes = _evenly_spaced_anchor_indexes(
            len(points),
            window_size=WINDOW_SIZE,
            max_points=max_points_per_vehicle,
        )

        for anchor_index in anchor_indexes:
            window = points[
                anchor_index - WINDOW_SIZE + 1:
                anchor_index + 1
            ]
            anchor = window[-1]

            try:
                features = extract_diagnostic_features(window)
            except ValueError:
                continue

            examples.append(
                DiagnosticExample(
                    vehicle_id=vehicle_id,
                    experiment_id=experiment_id,
                    anchor_timestamp=anchor.timestamp,
                    anchor_mileage=float(anchor.mileage),
                    label="healthy",
                    features=features,
                    miles_to_failure=None,
                )
            )

    return examples


def replace_extended_replay(
    run_id: int,
    *,
    replace_existing: bool,
    rows_per_vehicle: int = EXTENDED_ROWS_PER_VEHICLE,
    max_points_per_vehicle: int = EXTENDED_MAX_POINTS_PER_VEHICLE,
) -> dict:
    if rows_per_vehicle < WINDOW_SIZE:
        raise ValueError(
            f"rows_per_vehicle must be >= diagnostic window size {WINDOW_SIZE}"
        )
    if max_points_per_vehicle < 2:
        raise ValueError("max_points_per_vehicle must be >= 2")

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

        prediction_count = int(
            db.scalar(
                select(func.count(DiagnosticPrediction.id)).where(
                    DiagnosticPrediction.run_id == run.id
                )
            )
            or 0
        )
        if prediction_count < 1:
            return {
                "status": "waiting",
                "runId": run.id,
                "experimentId": run.experiment_id,
                "reason": "run has no persisted prediction anchors",
            }

        existing_count = int(
            db.scalar(
                select(func.count(DiagnosticReplayPoint.id)).where(
                    DiagnosticReplayPoint.run_id == run.id
                )
            )
            or 0
        )

        if existing_count > 0 and not replace_existing:
            return {
                "status": "replace_required",
                "runId": run.id,
                "experimentId": run.experiment_id,
                "existingReplayPoints": existing_count,
                "reason": (
                    "replay already exists; rerun with --replace-existing "
                    "to replace only this explicit run"
                ),
            }

        experiment_id = run.experiment_id
        lineage = run.lineage
        champion = run.champion
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

    if str(bundle.get("champion") or "") != champion:
        raise ValueError(
            "Model bundle champion does not match persisted diagnostic run"
        )

    feature_names = tuple(bundle.get("featureNames") or ())
    if not feature_names:
        raise ValueError("Model bundle is missing featureNames")

    model = _bundle_model(bundle, champion)

    with SessionLocal() as db:
        history = load_run_frozen_history(
            db,
            run_id=run_id,
            experiment_id=experiment_id,
            rows_per_vehicle=rows_per_vehicle,
        )

    examples = extended_replay_examples(
        history,
        experiment_id=experiment_id,
        max_points_per_vehicle=max_points_per_vehicle,
    )

    if not examples:
        return {
            "status": "waiting",
            "runId": run_id,
            "experimentId": experiment_id,
            "reason": "no eligible run-frozen observable replay windows",
        }

    ranked = predict_ranked_hypotheses(
        model,
        examples,
        feature_names=feature_names,
        top_k=3,
    )

    generated_at = datetime.now(timezone.utc)
    replay_rows = []

    for example, hypotheses in zip(examples, ranked):
        top = hypotheses[0]
        replay_rows.append(
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

    # Transactional explicit-run replacement. If insertion fails, deletion rolls
    # back too, preserving the previous replay.
    with SessionLocal() as db:
        db.execute(
            delete(DiagnosticReplayPoint).where(
                DiagnosticReplayPoint.run_id == run_id
            )
        )
        db.add_all(replay_rows)
        db.commit()

    points_per_vehicle = defaultdict(int)
    for row in replay_rows:
        points_per_vehicle[row.vehicle_id] += 1

    return {
        "status": "replaced",
        "runId": run_id,
        "experimentId": experiment_id,
        "lineage": lineage,
        "champion": champion,
        "previousReplayPoints": existing_count,
        "replayPoints": len(replay_rows),
        "vehicles": len(points_per_vehicle),
        "minPointsPerVehicle": min(points_per_vehicle.values(), default=0),
        "maxPointsPerVehicle": max(points_per_vehicle.values(), default=0),
        "history": {
            "rowsPerVehicleCap": rows_per_vehicle,
            "maxReplayPointsPerVehicle": max_points_per_vehicle,
            "upperCutoff": "persisted_diagnostic_prediction_anchor",
            "sampling": "deterministic_evenly_spaced_anchors",
        },
        "policy": {
            "runPinned": True,
            "exactExperimentOnly": True,
            "sameLineageOnly": True,
            "usesPrivateFailureTruth": False,
            "failureMarkersExposed": False,
            "usesPostRunTelemetry": False,
            "benchmarkModified": False,
            "modelRetrained": False,
        },
    }


def main() -> None:
    args = _parse_args()
    print(
        json.dumps(
            replace_extended_replay(
                args.run_id,
                replace_existing=args.replace_existing,
                rows_per_vehicle=args.rows_per_vehicle,
                max_points_per_vehicle=args.max_points_per_vehicle,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
