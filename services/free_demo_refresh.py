from __future__ import annotations

import importlib.util
import json
import os
import random
import sys
from pathlib import Path

from sqlalchemy import delete, func, select

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "services" / "common", ROOT / "services" / "ml"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from fleetmind_common.db import Base, SessionLocal, engine, ensure_schema_compatibility
from fleetmind_common.models import Alert, FailureEvent, Telemetry
from app import diagnostic_case_materialize
from app import diagnostic_episode_backfill
from app import diagnostic_event_backfill
from app import diagnostic_extended_replay_backfill
from app import diagnostic_run

EXPERIMENT_ID = os.getenv("FLEETMIND_DEMO_EXPERIMENT_ID", "exp-free-demo-v1")
VEHICLE_COUNT = max(60, int(os.getenv("FLEETMIND_DEMO_VEHICLES", "500")))
SAMPLES_PER_VEHICLE = max(24, int(os.getenv("FLEETMIND_DEMO_SAMPLES_PER_VEHICLE", "140")))
EVENTS_PER_SECOND = max(1, int(os.getenv("FLEETMIND_DEMO_EVENTS_PER_SECOND", "120")))
TIME_ACCELERATION = max(1.0, float(os.getenv("FLEETMIND_DEMO_TIME_ACCELERATION", "4800")))
SEED = int(os.getenv("FLEETMIND_DEMO_SEED", "20260824"))

EXPECTED_FAILURE_COMPONENTS = (
    "coolant_pump",
    "battery_pack",
    "inverter",
    "traction_motor",
    "coolant_temp_sensor",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SIM = load_module("fleetmind_demo_sim", ROOT / "services" / "simulator" / "app" / "sim.py")
WORKER = load_module("fleetmind_demo_worker", ROOT / "services" / "worker" / "app" / "main.py")


def reset_demo_source_data() -> dict:
    with SessionLocal() as db:
        telemetry = int(db.execute(delete(Telemetry).where(Telemetry.experiment_id == EXPERIMENT_ID)).rowcount or 0)
        failures = int(db.execute(delete(FailureEvent).where(FailureEvent.experiment_id == EXPERIMENT_ID)).rowcount or 0)
        alerts = int(db.execute(delete(Alert)).rowcount or 0)
        db.commit()
    return {"telemetryDeleted": telemetry, "failuresDeleted": failures, "alertsDeleted": alerts}


def generate_experiment() -> dict:
    fleet = SIM.build_fleet(VEHICLE_COUNT, SEED)
    rng = random.Random(SEED + 1)
    telemetry_rows = 0
    failure_events = 0
    failure_events_by_component = {
        component: 0 for component in EXPECTED_FAILURE_COMPONENTS
    }

    for sample_index in range(SAMPLES_PER_VEHICLE):
        batch = []
        failures = []
        for offset, vehicle in enumerate(fleet):
            step = SIM.sample_step(
                vehicle,
                sample_index * VEHICLE_COUNT + offset,
                VEHICLE_COUNT,
                EVENTS_PER_SECOND,
                rng,
                TIME_ACCELERATION,
            )
            step.telemetry["experimentId"] = EXPERIMENT_ID
            batch.append(step.telemetry)
            if step.failure_event is not None:
                step.failure_event["experimentId"] = EXPERIMENT_ID
                failures.append(step.failure_event)

        telemetry_rows += int(WORKER.persist_telemetry_batch(batch))
        for failure in failures:
            WORKER.persist_failure(failure)
            failure_events += 1
            component = str(failure.get("component") or "unknown")
            failure_events_by_component[component] = (
                failure_events_by_component.get(component, 0) + 1
            )

        if sample_index == 0 or (sample_index + 1) % 20 == 0 or sample_index + 1 == SAMPLES_PER_VEHICLE:
            print(
                f"demo generation sample={sample_index + 1}/{SAMPLES_PER_VEHICLE} "
                f"telemetry={telemetry_rows} failures={failure_events} "
                f"by_component={json.dumps(failure_events_by_component, sort_keys=True)}",
                flush=True,
            )

    return {
        "experimentId": EXPERIMENT_ID,
        "vehicles": VEHICLE_COUNT,
        "samplesPerVehicle": SAMPLES_PER_VEHICLE,
        "telemetryRows": telemetry_rows,
        "failureEvents": failure_events,
        "failureEventsByComponent": failure_events_by_component,
        "timeAcceleration": TIME_ACCELERATION,
        "seed": SEED,
    }


def validate_source_failure_coverage(generated: dict) -> dict:
    counts = generated.get("failureEventsByComponent") or {}
    missing = [
        component
        for component in EXPECTED_FAILURE_COMPONENTS
        if int(counts.get(component, 0) or 0) < 1
    ]
    if missing:
        raise RuntimeError(
            "Demo simulator did not produce source failure evidence for every "
            "diagnostic component. Missing="
            + json.dumps(missing)
            + " generated="
            + json.dumps(counts, sort_keys=True)
            + ". Increase simulated lifetime rather than weakening diagnostic gates."
        )
    return {
        "status": "covered",
        "requiredComponents": list(EXPECTED_FAILURE_COMPONENTS),
        "failureEventsByComponent": counts,
    }


def materialize_diagnostics() -> dict:
    report = diagnostic_run.run_once()
    run_id = report.get("diagnosticRunId")
    if not run_id:
        raise RuntimeError("Diagnostic trainer did not persist a run")
    if report.get("status") != "trained":
        raise RuntimeError(
            "Demo evidence did not satisfy the predeclared diagnostic development gate: "
            + json.dumps(
                {
                    "status": report.get("status"),
                    "dataset": report.get("dataset"),
                    "developmentReadiness": report.get("developmentReadiness"),
                },
                sort_keys=True,
                default=str,
            )
        )

    run_id = int(run_id)
    replay = diagnostic_extended_replay_backfill.replace_extended_replay(run_id, replace_existing=True)
    events = diagnostic_event_backfill.materialize_run(run_id, replace_existing=True)
    episodes = diagnostic_episode_backfill.materialize_run(run_id, replace_existing=True)
    cases = diagnostic_case_materialize.materialize_cases(run_id)
    return {
        "runId": run_id,
        "status": report.get("status"),
        "lineage": report.get("lineage"),
        "champion": (report.get("validation") or {}).get("champion"),
        "benchmarkQualification": report.get("benchmarkQualification"),
        "extendedReplay": replay,
        "events": events,
        "episodes": episodes,
        "cases": cases,
    }


def verify(run_id: int) -> dict:
    from fleetmind_common.diagnostic_store import DiagnosticModelRun, DiagnosticPrediction

    with SessionLocal() as db:
        telemetry = int(db.scalar(select(func.count(Telemetry.id)).where(Telemetry.experiment_id == EXPERIMENT_ID)) or 0)
        failures = int(db.scalar(select(func.count(FailureEvent.id)).where(FailureEvent.experiment_id == EXPERIMENT_ID)) or 0)
        predictions = int(
            db.scalar(
                select(func.count(DiagnosticPrediction.id)).where(
                    DiagnosticPrediction.run_id == run_id,
                    DiagnosticPrediction.experiment_id == EXPERIMENT_ID,
                )
            )
            or 0
        )
        run = db.get(DiagnosticModelRun, run_id)

    if run is None or run.status != "trained":
        raise RuntimeError(f"Diagnostic run {run_id} is not trained")
    if telemetry < VEHICLE_COUNT * 12:
        raise RuntimeError("Persisted demo telemetry is incomplete")
    if predictions < 1:
        raise RuntimeError("Trained demo run has no operational predictions")
    return {"telemetryRows": telemetry, "failureEvents": failures, "predictions": predictions}


def main() -> None:
    if not os.getenv("DATABASE_URL", "").strip():
        raise RuntimeError("DATABASE_URL is required")

    for key in ("DIAGNOSTIC_ARTIFACT_DIR", "ML_ARTIFACT_DIR"):
        if os.getenv(key):
            Path(os.environ[key]).mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    reset = reset_demo_source_data()
    generated = generate_experiment()
    source_failure_coverage = validate_source_failure_coverage(generated)
    diagnostics = materialize_diagnostics()
    verification = verify(int(diagnostics["runId"]))

    print(
        json.dumps(
            {
                "status": "complete",
                "mode": "scheduled_free_demo",
                "reset": reset,
                "generated": generated,
                "sourceFailureCoverage": source_failure_coverage,
                "diagnostics": diagnostics,
                "verification": verification,
                "interpretationPolicy": (
                    "Deterministic synthetic demo telemetry and derived diagnostic state; "
                    "not live vehicle telemetry or physical failure probability."
                ),
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
