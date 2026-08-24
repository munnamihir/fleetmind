from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import desc, select

from fleetmind_common.db import Base, SessionLocal, engine
from fleetmind_common.ml_features import (
    FailureTruth,
    TelemetryPoint,
    build_feature_examples,
    latest_feature_examples,
    split_examples_frozen_benchmark,
)
from fleetmind_common.models import FailureEvent, MLModelRun, MLPrediction, Telemetry
from app.training import (
    examples_to_frame,
    json_dumps,
    metric_delta,
    save_artifact,
    train_logistic_baseline,
    train_xgboost,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fleetmind-ml")

HORIZON_MILES = float(os.getenv("ML_FAILURE_HORIZON_MILES", "2500"))
WINDOW_SIZE = int(os.getenv("ML_WINDOW_SIZE", "12"))
STRIDE = int(os.getenv("ML_WINDOW_STRIDE", "4"))
MAX_EXAMPLES_PER_VEHICLE = int(os.getenv("ML_MAX_EXAMPLES_PER_VEHICLE", "32"))
MAX_TELEMETRY_ROWS = int(os.getenv("ML_MAX_TELEMETRY_ROWS", "250000"))
TRAIN_INTERVAL_SECONDS = int(os.getenv("ML_TRAIN_INTERVAL_SECONDS", "90"))
STARTUP_DELAY_SECONDS = int(os.getenv("ML_STARTUP_DELAY_SECONDS", "20"))
MIN_TRAIN_EXAMPLES = int(os.getenv("ML_MIN_TRAIN_EXAMPLES", "500"))
MIN_TRAIN_POSITIVES = int(os.getenv("ML_MIN_TRAIN_POSITIVES", "5"))
MIN_VALIDATION_EXAMPLES = int(os.getenv("ML_MIN_VALIDATION_EXAMPLES", "80"))
ARTIFACT_DIR = Path(os.getenv("ML_ARTIFACT_DIR", "/artifacts"))

# Phase 5.1 benchmark policy. These defaults intentionally live in the trainer so
# the upgrade does not require another docker-compose merge.
BENCHMARK_SEED = int(os.getenv("ML_BENCHMARK_SEED", "20260824"))
BENCHMARK_FRACTION = float(os.getenv("ML_BENCHMARK_FRACTION", "0.20"))
VALIDATION_FRACTION = float(os.getenv("ML_VALIDATION_FRACTION", "0.15"))
HELDOUT_TAIL_FRACTION = float(os.getenv("ML_HELDOUT_TAIL_FRACTION", "0.75"))
MIN_BENCHMARK_EXAMPLES = int(os.getenv("ML_MIN_BENCHMARK_EXAMPLES", "1000"))
MIN_BENCHMARK_POSITIVES = int(os.getenv("ML_MIN_BENCHMARK_POSITIVES", "20"))
MIN_BENCHMARK_FAILURE_VEHICLES = int(
    os.getenv("ML_MIN_BENCHMARK_FAILURE_VEHICLES", "8")
)


def telemetry_point(row: Telemetry) -> TelemetryPoint:
    return TelemetryPoint(
        timestamp=row.timestamp,
        vehicle_id=row.vehicle_id,
        model=row.model,
        factory=row.factory,
        firmware=row.firmware,
        pump_revision=row.pump_revision,
        mileage=float(row.mileage),
        ambient_temp_c=float(row.ambient_temp_c),
        speed_mph=float(row.speed_mph),
        battery_temp_c=float(row.battery_temp_c),
        cell_imbalance_v=float(row.cell_imbalance_v),
        inverter_temp_c=float(row.inverter_temp_c),
        coolant_temp_c=float(row.coolant_temp_c),
        pump_rpm=float(row.pump_rpm),
        pump_current_a=float(row.pump_current_a),
    )


def load_training_data(db):
    telemetry_rows = db.execute(
        select(Telemetry).order_by(desc(Telemetry.id)).limit(MAX_TELEMETRY_ROWS)
    ).scalars().all()
    telemetry_rows.reverse()

    by_vehicle: dict[str, list[TelemetryPoint]] = defaultdict(list)
    for row in telemetry_rows:
        point = telemetry_point(row)
        by_vehicle[point.vehicle_id].append(point)

    failure_rows = db.execute(select(FailureEvent)).scalars().all()
    failures = {
        row.vehicle_id: FailureTruth(
            vehicle_id=row.vehicle_id,
            failure_mileage=float(row.failure_mileage),
            occurred_at=row.occurred_at,
        )
        for row in failure_rows
    }
    return by_vehicle, failures


def dataset_summary(split) -> dict:
    def block(rows):
        return {
            "examples": len(rows),
            "positives": sum(row.label for row in rows),
            "vehicles": len({row.vehicle_id for row in rows}),
            "failureVehicles": len({row.vehicle_id for row in rows if row.label == 1}),
        }

    return {
        "train": block(split.train),
        "validation": block(split.validation),
        "benchmark": block(split.benchmark),
    }


def insufficient_reason(summary: dict) -> str | None:
    if summary["train"]["examples"] < MIN_TRAIN_EXAMPLES:
        return f"need at least {MIN_TRAIN_EXAMPLES} train examples"
    if summary["train"]["positives"] < MIN_TRAIN_POSITIVES:
        return f"need at least {MIN_TRAIN_POSITIVES} positive train examples"
    if summary["validation"]["examples"] < MIN_VALIDATION_EXAMPLES:
        return f"need at least {MIN_VALIDATION_EXAMPLES} validation examples"
    if summary["validation"]["positives"] < 1:
        return "waiting for at least one positive validation window"
    if summary["benchmark"]["examples"] < 1:
        return "waiting for frozen benchmark examples"
    return None


def benchmark_qualification(summary: dict) -> dict:
    observed = summary["benchmark"]
    requirements = {
        "examples": MIN_BENCHMARK_EXAMPLES,
        "positiveWindows": MIN_BENCHMARK_POSITIVES,
        "failureVehicles": MIN_BENCHMARK_FAILURE_VEHICLES,
        "bothClassesPresent": True,
    }
    reasons: list[str] = []
    if observed["examples"] < MIN_BENCHMARK_EXAMPLES:
        reasons.append(
            f"benchmark examples {observed['examples']} < {MIN_BENCHMARK_EXAMPLES}"
        )
    if observed["positives"] < MIN_BENCHMARK_POSITIVES:
        reasons.append(
            f"positive windows {observed['positives']} < {MIN_BENCHMARK_POSITIVES}"
        )
    if observed["failureVehicles"] < MIN_BENCHMARK_FAILURE_VEHICLES:
        reasons.append(
            f"failure vehicles {observed['failureVehicles']} < {MIN_BENCHMARK_FAILURE_VEHICLES}"
        )
    both_classes = 0 < observed["positives"] < observed["examples"]
    if not both_classes:
        reasons.append("benchmark must contain both outcome classes")

    return {
        "status": "qualified" if not reasons else "insufficient_evidence",
        "requirements": requirements,
        "observed": {
            **observed,
            "bothClassesPresent": both_classes,
        },
        "reasons": reasons,
        "claimPolicy": (
            "Headline benchmark metrics are publishable only when the frozen benchmark "
            "meets every evidence requirement. Operational scoring may continue regardless."
        ),
    }


def create_run(db, status: str, summary: dict, notes: str = "") -> MLModelRun:
    now = datetime.now(timezone.utc)
    benchmark = summary["benchmark"]
    run = MLModelRun(
        created_at=now,
        completed_at=now if status != "training" else None,
        status=status,
        algorithm="Sensor-only XGBoost + logistic baseline | frozen benchmark",
        horizon_miles=HORIZON_MILES,
        window_size=WINDOW_SIZE,
        train_examples=summary["train"]["examples"],
        validation_examples=summary["validation"]["examples"],
        # Existing schema's test_* columns now store the frozen benchmark counts.
        test_examples=benchmark["examples"],
        train_positives=summary["train"]["positives"],
        validation_positives=summary["validation"]["positives"],
        test_positives=benchmark["positives"],
        leakage_policy_json=json_dumps(
            {
                "vehicleIsolation": True,
                "frozenBenchmark": True,
                "benchmarkMembershipDependsOnlyOnVehicleId": True,
                "benchmarkSeed": BENCHMARK_SEED,
                "benchmarkFraction": BENCHMARK_FRACTION,
                "validationFraction": VALIDATION_FRACTION,
                "heldOutLateLifeWindows": True,
                "rightCensoringProtection": True,
                "benchmarkUsedForFit": False,
                "benchmarkUsedForCalibration": False,
                "benchmarkUsedForThresholdSelection": False,
                "forbiddenInputs": [
                    "vehicle_id",
                    "timestamp",
                    "risk_score",
                    "status",
                    "alerts",
                    "fault_codes",
                    "failure_events",
                ],
                "contextFieldsExcludedFromModelFit": [
                    "model",
                    "factory",
                    "firmware",
                    "pump_revision",
                ],
                "labelDefinition": f"component failure within next {HORIZON_MILES:.0f} miles",
            }
        ),
        notes=notes,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def prediction_summary(features: dict) -> dict:
    keys = [
        "pump_current_a_last",
        "pump_current_a_slope_per_1k_mi",
        "pump_rpm_last",
        "pump_rpm_slope_per_1k_mi",
        "coolant_temp_c_last",
        "battery_temp_c_last",
    ]
    return {key: round(float(features[key]), 5) for key in keys if key in features}


def train_once() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        by_vehicle, failures = load_training_data(db)
        examples = build_feature_examples(
            by_vehicle,
            failures,
            horizon_miles=HORIZON_MILES,
            window_size=WINDOW_SIZE,
            stride=STRIDE,
            max_examples_per_vehicle=MAX_EXAMPLES_PER_VEHICLE,
        )
        split = split_examples_frozen_benchmark(
            examples,
            seed=BENCHMARK_SEED,
            benchmark_fraction=BENCHMARK_FRACTION,
            validation_fraction=VALIDATION_FRACTION,
            heldout_tail_fraction=HELDOUT_TAIL_FRACTION,
        )
        summary = dataset_summary(split)
        reason = insufficient_reason(summary)
        if reason:
            create_run(db, "insufficient_data", summary, reason)
            log.info("ML waiting: %s | dataset=%s", reason, summary)
            return

        qualification = benchmark_qualification(summary)
        run = create_run(db, "training", summary)
        log.info(
            "training Phase 5.1 run=%s dataset=%s benchmark=%s",
            run.id,
            summary,
            qualification["status"],
        )

        xgboost_model = train_xgboost(split.train, split.validation, split.benchmark)
        logistic_model = train_logistic_baseline(
            split.train, split.validation, split.benchmark
        )

        xgb_artifact = ARTIFACT_DIR / f"fleetmind-xgb-run-{run.id}.joblib"
        baseline_artifact = ARTIFACT_DIR / f"fleetmind-logistic-run-{run.id}.joblib"
        metadata = {
            "runId": run.id,
            "horizonMiles": HORIZON_MILES,
            "windowSize": WINDOW_SIZE,
            "dataset": summary,
            "benchmarkQualification": qualification,
            "benchmarkSeed": BENCHMARK_SEED,
        }
        save_artifact(xgboost_model, xgb_artifact, {**metadata, "model": "xgboost"})
        save_artifact(
            logistic_model, baseline_artifact, {**metadata, "model": "logistic_baseline"}
        )

        metrics = dict(xgboost_model.metrics)
        metrics["benchmarkQualification"] = qualification
        metrics["baseline"] = {
            "algorithm": "Logistic regression · identical sensor features/cohorts",
            **logistic_model.metrics,
        }
        metrics["modelDeltaVsBaseline"] = metric_delta(
            xgboost_model.metrics, logistic_model.metrics
        )
        metrics["benchmarkProtocol"] = {
            "name": "frozen vehicle benchmark",
            "seed": BENCHMARK_SEED,
            "fraction": BENCHMARK_FRACTION,
            "membership": "SHA-256(vehicle_id, fixed seed); label-agnostic and stable across runs",
            "fit": "development train vehicles only",
            "calibration": "development validation vehicles only",
            "threshold": "development validation negatives only",
            "evaluation": "frozen benchmark late-life causal windows only",
        }
        metrics["operationalScoring"] = {
            "model": "xgboost",
            "scope": "latest causal window for every active vehicle",
            "benchmarkQualificationRequired": False,
        }

        run.status = "complete"
        run.completed_at = datetime.now(timezone.utc)
        run.decision_threshold = float(xgboost_model.threshold)
        run.metrics_json = json_dumps(metrics)
        run.calibration_json = json_dumps(xgboost_model.calibration_bins)
        run.feature_importance_json = json_dumps(xgboost_model.feature_importance)
        run.notes = f"xgboost={xgb_artifact}; baseline={baseline_artifact}"
        db.commit()

        # Operational scoring stays separate from the benchmark: score one latest
        # causal window per active vehicle using the XGBoost production candidate.
        latest = latest_feature_examples(by_vehicle, window_size=WINDOW_SIZE)
        frame, _ = examples_to_frame(latest)
        if not frame.empty:
            probabilities = xgboost_model.predict_proba(frame)
            generated_at = datetime.now(timezone.utc)
            for example, probability in zip(latest, probabilities.tolist()):
                features = example.features
                db.add(
                    MLPrediction(
                        model_run_id=run.id,
                        generated_at=generated_at,
                        vehicle_id=example.vehicle_id,
                        probability=float(probability),
                        predicted_label=int(probability >= xgboost_model.threshold),
                        anchor_mileage=example.anchor_mileage,
                        firmware=str(features["firmware"]),
                        pump_revision=str(features["pump_revision"]),
                        factory=str(features["factory"]),
                        model=str(features["model"]),
                        feature_summary_json=json_dumps(prediction_summary(features)),
                    )
                )
            db.commit()

        log.info(
            "ML run=%s complete benchmark=%s XGB PR-AUC=%s baseline PR-AUC=%s recall=%.3f threshold=%.3f predictions=%s",
            run.id,
            qualification["status"],
            xgboost_model.metrics.get("prAuc"),
            logistic_model.metrics.get("prAuc"),
            xgboost_model.metrics.get("recall", 0.0),
            xgboost_model.threshold,
            len(latest),
        )
    except Exception as exc:
        db.rollback()
        log.exception("ML training cycle failed: %s", exc)
        try:
            empty = {
                name: {
                    "examples": 0,
                    "positives": 0,
                    "vehicles": 0,
                    "failureVehicles": 0,
                }
                for name in ("train", "validation", "benchmark")
            }
            create_run(db, "failed", empty, str(exc)[:1000])
        except Exception:
            db.rollback()
    finally:
        db.close()


def main() -> None:
    log.info(
        "FleetMind ML trainer starting horizon=%.0fmi window=%s stride=%s interval=%ss frozen-benchmark=%.0f%%",
        HORIZON_MILES,
        WINDOW_SIZE,
        STRIDE,
        TRAIN_INTERVAL_SECONDS,
        BENCHMARK_FRACTION * 100.0,
    )
    time.sleep(max(0, STARTUP_DELAY_SECONDS))
    while True:
        train_once()
        time.sleep(max(15, TRAIN_INTERVAL_SECONDS))


if __name__ == "__main__":
    main()
