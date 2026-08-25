from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

import joblib
import numpy as np
from sqlalchemy import text

from fleetmind_common.db import SessionLocal
from fleetmind_common.diagnostic_benchmark_snapshot import (
    load_snapshot as load_diagnostic_snapshot,
    save_snapshot_once as save_diagnostic_snapshot_once,
)
from fleetmind_common.diagnostic_dataset import (
    DIAGNOSTIC_CLASSES,
    DEFAULT_DIAGNOSTIC_HORIZON_MILES,
    DEFAULT_DIAGNOSTIC_STRIDE,
    DEFAULT_DIAGNOSTIC_WINDOW_SIZE,
    DEFAULT_MAX_EXAMPLES_PER_VEHICLE,
    DiagnosticExample,
    DiagnosticFailureTruth,
    build_diagnostic_examples,
    qualify_diagnostic_benchmark,
    split_diagnostic_examples,
)
from fleetmind_common.diagnostics import DiagnosticTelemetryPoint
from app.diagnostic_models import (
    DIAGNOSTIC_MODEL_LINEAGE,
    TransparentDiagnosticBaseline,
    evaluate_diagnostic_probabilities,
    fit_compare_diagnostic_models,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("fleetmind-diagnostics-trainer")

HORIZON_MILES = float(
    os.getenv(
        "DIAGNOSTIC_HORIZON_MILES",
        str(DEFAULT_DIAGNOSTIC_HORIZON_MILES),
    )
)
WINDOW_SIZE = int(
    os.getenv(
        "DIAGNOSTIC_WINDOW_SIZE",
        str(DEFAULT_DIAGNOSTIC_WINDOW_SIZE),
    )
)
STRIDE = int(
    os.getenv(
        "DIAGNOSTIC_WINDOW_STRIDE",
        str(DEFAULT_DIAGNOSTIC_STRIDE),
    )
)
MAX_EXAMPLES_PER_VEHICLE = int(
    os.getenv(
        "DIAGNOSTIC_MAX_EXAMPLES_PER_VEHICLE",
        str(DEFAULT_MAX_EXAMPLES_PER_VEHICLE),
    )
)
MAX_TELEMETRY_ROWS = int(
    os.getenv("DIAGNOSTIC_MAX_TELEMETRY_ROWS", "300000")
)
BENCHMARK_FRACTION = float(
    os.getenv("DIAGNOSTIC_BENCHMARK_FRACTION", "0.20")
)
VALIDATION_FRACTION = float(
    os.getenv("DIAGNOSTIC_VALIDATION_FRACTION", "0.20")
)

# Development readiness is separate from frozen benchmark qualification.
# These values are declared before metrics are observed and should not be
# weakened after seeing results.
MIN_TRAIN_EXAMPLES = int(
    os.getenv("DIAGNOSTIC_MIN_TRAIN_EXAMPLES", "500")
)
MIN_VALIDATION_EXAMPLES = int(
    os.getenv("DIAGNOSTIC_MIN_VALIDATION_EXAMPLES", "100")
)
MIN_TRAIN_VEHICLES_PER_CLASS = int(
    os.getenv("DIAGNOSTIC_MIN_TRAIN_VEHICLES_PER_CLASS", "3")
)
MIN_VALIDATION_VEHICLES_PER_CLASS = int(
    os.getenv("DIAGNOSTIC_MIN_VALIDATION_VEHICLES_PER_CLASS", "1")
)

ARTIFACT_DIR = Path(
    os.getenv("DIAGNOSTIC_ARTIFACT_DIR", "/artifacts/diagnostics")
)


def benchmark_snapshot_path(experiment_id: str) -> Path:
    return (
        ARTIFACT_DIR
        / _safe_path_segment(DIAGNOSTIC_MODEL_LINEAGE)
        / _safe_path_segment(experiment_id)
        / "benchmark-v1.json.gz"
    )


def benchmark_snapshot_metadata(
    experiment_id: str,
    qualification,
) -> dict:
    return {
        "lineage": DIAGNOSTIC_MODEL_LINEAGE,
        "experimentId": experiment_id,
        "lockedAt": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "horizonMiles": HORIZON_MILES,
            "windowSize": WINDOW_SIZE,
            "stride": STRIDE,
            "maxExamplesPerVehicle": MAX_EXAMPLES_PER_VEHICLE,
            "benchmarkFraction": BENCHMARK_FRACTION,
        },
        "qualificationAtLock": {
            "status": qualification.status,
            "examples": qualification.examples,
            "vehicles": qualification.vehicles,
            "examplesByClass": qualification.examples_by_class,
            "vehiclesByClass": qualification.vehicles_by_class,
        },
    }


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dict__"):
        return value.__dict__
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _safe_path_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return cleaned or "unknown"


def _metric_payload(metrics) -> dict:
    return {
        "macroF1": metrics.macro_f1,
        "balancedAccuracy": metrics.balanced_accuracy,
        "top2Accuracy": metrics.top2_accuracy,
        "multiclassBrier": metrics.multiclass_brier,
        "perClass": metrics.per_class,
        "confusionMatrix": metrics.confusion_matrix,
    }


def _split_summary(examples: Sequence[DiagnosticExample]) -> dict:
    examples_by_class = {
        label: 0
        for label in DIAGNOSTIC_CLASSES
    }
    vehicle_sets = {
        label: set()
        for label in DIAGNOSTIC_CLASSES
    }

    for example in examples:
        examples_by_class[example.label] += 1
        vehicle_sets[example.label].add(example.vehicle_id)

    return {
        "examples": len(examples),
        "vehicles": len({example.vehicle_id for example in examples}),
        "examplesByClass": examples_by_class,
        "vehiclesByClass": {
            label: len(vehicle_sets[label])
            for label in DIAGNOSTIC_CLASSES
        },
    }


def _development_readiness(
    train: Sequence[DiagnosticExample],
    validation: Sequence[DiagnosticExample],
) -> dict:
    train_summary = _split_summary(train)
    validation_summary = _split_summary(validation)

    reasons: List[str] = []

    if train_summary["examples"] < MIN_TRAIN_EXAMPLES:
        reasons.append(
            f"train examples {train_summary['examples']} "
            f"< required {MIN_TRAIN_EXAMPLES}"
        )

    if validation_summary["examples"] < MIN_VALIDATION_EXAMPLES:
        reasons.append(
            f"validation examples {validation_summary['examples']} "
            f"< required {MIN_VALIDATION_EXAMPLES}"
        )

    for label in DIAGNOSTIC_CLASSES:
        train_vehicles = train_summary["vehiclesByClass"][label]
        validation_vehicles = validation_summary["vehiclesByClass"][label]

        if train_vehicles < MIN_TRAIN_VEHICLES_PER_CLASS:
            reasons.append(
                f"train {label} vehicles {train_vehicles} "
                f"< required {MIN_TRAIN_VEHICLES_PER_CLASS}"
            )

        if validation_vehicles < MIN_VALIDATION_VEHICLES_PER_CLASS:
            reasons.append(
                f"validation {label} vehicles {validation_vehicles} "
                f"< required {MIN_VALIDATION_VEHICLES_PER_CLASS}"
            )

    return {
        "status": "ready" if not reasons else "insufficient_evidence",
        "reasons": reasons,
        "requirements": {
            "trainExamples": MIN_TRAIN_EXAMPLES,
            "validationExamples": MIN_VALIDATION_EXAMPLES,
            "trainVehiclesPerClass": MIN_TRAIN_VEHICLES_PER_CLASS,
            "validationVehiclesPerClass": MIN_VALIDATION_VEHICLES_PER_CLASS,
        },
        "train": train_summary,
        "validation": validation_summary,
    }


def active_experiment_id(db) -> str | None:
    return db.execute(
        text(
            """
            SELECT experiment_id
            FROM telemetry
            WHERE experiment_id IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """
        )
    ).scalar_one_or_none()


def load_active_experiment(db, experiment_id: str):
    telemetry_rows = db.execute(
        text(
            """
            SELECT
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
            FROM (
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
                FROM telemetry
                WHERE experiment_id = :experiment_id
                ORDER BY id DESC
                LIMIT :max_rows
            ) recent
            ORDER BY vehicle_id, timestamp
            """
        ),
        {
            "experiment_id": experiment_id,
            "max_rows": MAX_TELEMETRY_ROWS,
        },
    ).mappings().all()

    by_vehicle: Dict[str, List[DiagnosticTelemetryPoint]] = defaultdict(list)

    for row in telemetry_rows:
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

    failure_rows = db.execute(
        text(
            """
            SELECT
                vehicle_id,
                experiment_id,
                component,
                failure_mileage,
                occurred_at
            FROM failure_events
            WHERE experiment_id = :experiment_id
            ORDER BY occurred_at, vehicle_id
            """
        ),
        {"experiment_id": experiment_id},
    ).mappings().all()

    failures = [
        DiagnosticFailureTruth(
            vehicle_id=row["vehicle_id"],
            experiment_id=row["experiment_id"],
            component=row["component"],
            failure_mileage=float(row["failure_mileage"]),
            occurred_at=row["occurred_at"],
        )
        for row in failure_rows
    ]

    return by_vehicle, failures


def _aligned_probabilities(
    model,
    examples: Sequence[DiagnosticExample],
    feature_names: Sequence[str],
) -> np.ndarray:
    if isinstance(model, TransparentDiagnosticBaseline):
        return model.predict_proba(examples)

    matrix = np.asarray(
        [
            [
                float(example.features[name])
                for name in feature_names
            ]
            for example in examples
        ],
        dtype=float,
    )

    raw = model.predict_proba(matrix)
    aligned = np.zeros(
        (len(examples), len(DIAGNOSTIC_CLASSES)),
        dtype=float,
    )

    for source_index, class_index in enumerate(model.classes_):
        aligned[:, int(class_index)] = raw[:, source_index]

    totals = aligned.sum(axis=1, keepdims=True)
    totals[totals <= 0.0] = 1.0
    return aligned / totals


def evaluate_models(
    baseline,
    logistic,
    xgboost,
    examples: Sequence[DiagnosticExample],
    feature_names: Sequence[str],
) -> dict:
    result = {}
    for name, model in (
        ("transparentBaseline", baseline),
        ("multinomialLogistic", logistic),
        ("xgboostMulticlass", xgboost),
    ):
        probabilities = _aligned_probabilities(
            model,
            examples,
            feature_names,
        )
        result[name] = _metric_payload(
            evaluate_diagnostic_probabilities(
                examples,
                probabilities,
            )
        )
    return result


def save_artifacts(
    *,
    experiment_id: str,
    baseline,
    logistic,
    xgboost,
    comparison,
    report: dict,
) -> dict:
    destination = (
        ARTIFACT_DIR
        / _safe_path_segment(DIAGNOSTIC_MODEL_LINEAGE)
        / _safe_path_segment(experiment_id)
    )
    destination.mkdir(parents=True, exist_ok=True)

    bundle_path = destination / "diagnostic-model-bundle.joblib"
    report_path = destination / "diagnostic-report.json"

    bundle = {
        "lineage": DIAGNOSTIC_MODEL_LINEAGE,
        "experimentId": experiment_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "classes": list(DIAGNOSTIC_CLASSES),
        "featureNames": list(comparison.feature_names),
        "featureSchemaSha256": comparison.feature_schema_hash,
        "champion": comparison.champion,
        "transparentBaseline": baseline,
        "multinomialLogistic": logistic,
        "xgboostMulticlass": xgboost,
    }

    artifact_paths = {
        "bundlePath": str(bundle_path),
        "reportPath": str(report_path),
    }

    joblib.dump(bundle, bundle_path)

    persisted_report = dict(report)
    persisted_report["artifacts"] = artifact_paths
    report_path.write_text(
        json.dumps(
            persisted_report,
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
        + "\n"
    )

    return artifact_paths


def run_once() -> dict:
    with SessionLocal() as db:
        experiment_id = active_experiment_id(db)
        if not experiment_id:
            return {
                "status": "waiting",
                "reason": "no tagged telemetry experiment is available",
                "lineage": DIAGNOSTIC_MODEL_LINEAGE,
            }

        by_vehicle, failures = load_active_experiment(
            db,
            experiment_id,
        )

    telemetry_rows = sum(len(points) for points in by_vehicle.values())

    examples = build_diagnostic_examples(
        by_vehicle,
        failures,
        experiment_id=experiment_id,
        horizon_miles=HORIZON_MILES,
        window_size=WINDOW_SIZE,
        stride=STRIDE,
        max_examples_per_vehicle=MAX_EXAMPLES_PER_VEHICLE,
    )

    split = split_diagnostic_examples(
        examples,
        benchmark_fraction=BENCHMARK_FRACTION,
        validation_fraction=VALIDATION_FRACTION,
    )

    development = _development_readiness(
        split.train,
        split.validation,
    )
    current_benchmark_qualification = qualify_diagnostic_benchmark(
        split.benchmark
    )

    snapshot_path = benchmark_snapshot_path(experiment_id)
    snapshot_status = "accumulating"
    snapshot_integrity = None
    benchmark_examples = list(split.benchmark)

    if snapshot_path.exists():
        benchmark_examples, snapshot_integrity = load_diagnostic_snapshot(
            snapshot_path,
            expected_experiment_id=experiment_id,
            expected_lineage=DIAGNOSTIC_MODEL_LINEAGE,
        )
        snapshot_status = "locked"
    elif current_benchmark_qualification.status == "qualified":
        save_diagnostic_snapshot_once(
            split.benchmark,
            snapshot_path,
            benchmark_snapshot_metadata(
                experiment_id,
                current_benchmark_qualification,
            ),
        )
        benchmark_examples, snapshot_integrity = load_diagnostic_snapshot(
            snapshot_path,
            expected_experiment_id=experiment_id,
            expected_lineage=DIAGNOSTIC_MODEL_LINEAGE,
        )
        snapshot_status = "locked"

    benchmark_qualification = qualify_diagnostic_benchmark(
        benchmark_examples
    )

    report = {
        "status": "waiting",
        "lineage": DIAGNOSTIC_MODEL_LINEAGE,
        "experimentId": experiment_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "horizonMiles": HORIZON_MILES,
            "windowSize": WINDOW_SIZE,
            "stride": STRIDE,
            "maxExamplesPerVehicle": MAX_EXAMPLES_PER_VEHICLE,
            "benchmarkFraction": BENCHMARK_FRACTION,
            "validationFraction": VALIDATION_FRACTION,
            "maxTelemetryRows": MAX_TELEMETRY_ROWS,
        },
        "source": {
            "telemetryRowsLoaded": telemetry_rows,
            "vehiclesLoaded": len(by_vehicle),
            "failureEventsLoaded": len(failures),
            "failureVehiclesLoaded": len(
                {failure.vehicle_id for failure in failures}
            ),
            "failureComponents": {
                label: sum(
                    1
                    for failure in failures
                    if failure.component == label
                )
                for label in DIAGNOSTIC_CLASSES
                if label != "healthy"
            },
        },
        "dataset": {
            "totalExamples": len(examples),
            "train": _split_summary(split.train),
            "validation": _split_summary(split.validation),
            "benchmark": _split_summary(benchmark_examples),
        },
        "developmentReadiness": development,
        "benchmarkSnapshot": {
            "status": snapshot_status,
            "artifactPath": (
                str(snapshot_path)
                if snapshot_status == "locked"
                else None
            ),
            "sha256": (
                snapshot_integrity["sha256"]
                if snapshot_integrity is not None
                else None
            ),
            "featureSchemaSha256": (
                snapshot_integrity["featureSchemaSha256"]
                if snapshot_integrity is not None
                else None
            ),
            "message": (
                "Exact benchmark examples are immutable for this "
                "lineage/experiment."
                if snapshot_status == "locked"
                else
                "Vehicle membership is frozen; eligible windows continue "
                "accumulating until the evidence gate qualifies."
            ),
        },
        "benchmarkQualification": {
            "status": benchmark_qualification.status,
            "reasons": list(benchmark_qualification.reasons),
            "examples": benchmark_qualification.examples,
            "vehicles": benchmark_qualification.vehicles,
            "examplesByClass": benchmark_qualification.examples_by_class,
            "vehiclesByClass": benchmark_qualification.vehicles_by_class,
            "claimPolicy": (
                "Frozen benchmark model metrics are withheld until every "
                "predeclared per-class evidence requirement passes."
            ),
        },
    }

    if development["status"] != "ready":
        report["status"] = "insufficient_development_evidence"
        return report

    baseline, logistic, xgboost, comparison = (
        fit_compare_diagnostic_models(
            split.train,
            split.validation,
        )
    )

    report["status"] = "trained"
    report["featureSchemaSha256"] = comparison.feature_schema_hash
    report["featureCount"] = len(comparison.feature_names)
    report["validation"] = {
        "champion": comparison.champion,
        "models": {
            "transparentBaseline": _metric_payload(
                comparison.baseline_metrics
            ),
            "multinomialLogistic": _metric_payload(
                comparison.logistic_metrics
            ),
            "xgboostMulticlass": _metric_payload(
                comparison.xgboost_metrics
            ),
        },
    }

    # The benchmark is not used for model selection. It is evaluated only
    # after its fixed evidence gate qualifies.
    if benchmark_qualification.status == "qualified":
        report["benchmark"] = {
            "status": "qualified",
            "models": evaluate_models(
                baseline,
                logistic,
                xgboost,
                benchmark_examples,
                comparison.feature_names,
            ),
        }
    else:
        report["benchmark"] = {
            "status": "withheld_insufficient_evidence",
            "models": None,
        }

    report["artifacts"] = save_artifacts(
        experiment_id=experiment_id,
        baseline=baseline,
        logistic=logistic,
        xgboost=xgboost,
        comparison=comparison,
        report=report,
    )

    return report


def main() -> None:
    report = run_once()
    print(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
    )


if __name__ == "__main__":
    main()
