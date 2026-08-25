from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaError
from sqlalchemy import select

from fleetmind_common.config import FAILURE_TOPIC, KAFKA_BOOTSTRAP_SERVERS, TELEMETRY_TOPIC
from fleetmind_common.db import Base, SessionLocal, engine, ensure_schema_compatibility
from fleetmind_common.models import Alert, FailureEvent, Telemetry
from fleetmind_common.risk import score_telemetry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fleetmind-worker")

last_alert_at: dict[str, float] = {}
ALERT_COOLDOWN_SECONDS = 25

WORKER_BATCH_SIZE = max(1, int(os.getenv("WORKER_BATCH_SIZE", "500")))
WORKER_BATCH_TIMEOUT_SECONDS = max(
    0.05, float(os.getenv("WORKER_BATCH_TIMEOUT_SECONDS", "1.0"))
)
WORKER_STATS_INTERVAL_SECONDS = max(
    5.0, float(os.getenv("WORKER_STATS_INTERVAL_SECONDS", "15"))
)


def wait_for_db() -> None:
    for attempt in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            ensure_schema_compatibility()
            return
        except Exception as exc:
            log.warning("database not ready (%s/30): %s", attempt + 1, exc)
            time.sleep(2)
    raise RuntimeError("database unavailable")


def build_telemetry_record(event: dict, now: float):
    risk = score_telemetry(event)
    battery = event["battery"]
    powertrain = event["powertrain"]
    thermal = event["thermal"]
    vehicle = event["vehicle"]

    ts = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    row = Telemetry(
        timestamp=ts,
        experiment_id=event.get("experimentId"),
        vehicle_id=vehicle["id"],
        model=vehicle["model"],
        factory=vehicle["factory"],
        firmware=vehicle["firmware"],
        pump_revision=vehicle["pumpRevision"],
        mileage=float(vehicle["mileage"]),
        ambient_temp_c=float(event["ambientTempC"]),
        speed_mph=float(event["speedMph"]),
        soc_pct=float(battery["socPct"]),
        pack_voltage_v=float(battery["packVoltageV"]),
        pack_current_a=float(battery["packCurrentA"]),
        battery_temp_c=float(battery["temperatureC"]),
        cell_imbalance_v=float(battery["cellImbalanceV"]),
        motor_temp_c=float(powertrain["motorTempC"]),
        inverter_temp_c=float(powertrain["inverterTempC"]),
        motor_rpm=float(powertrain["motorRPM"]),
        coolant_temp_c=float(thermal["coolantTempC"]),
        pump_rpm=float(thermal["pumpRPM"]),
        pump_current_a=float(thermal["pumpCurrentA"]),
        risk_score=risk.score,
        status=risk.status,
    )

    should_alert = (
        risk.status != "healthy"
        and now - last_alert_at.get(vehicle["id"], 0) >= ALERT_COOLDOWN_SECONDS
    )

    alert = None
    if should_alert:
        alert = Alert(
            created_at=datetime.now(timezone.utc),
            vehicle_id=vehicle["id"],
            severity=risk.severity,
            risk_score=risk.score,
            title="Thermal system degradation signature detected",
            evidence=" | ".join(risk.evidence),
            firmware=vehicle["firmware"],
            pump_revision=vehicle["pumpRevision"],
            factory=vehicle["factory"],
        )

    return row, alert, vehicle["id"] if should_alert else None


def persist_telemetry_batch(events: list[dict]) -> int:
    if not events:
        return 0

    now = time.time()
    rows: list[Telemetry] = []
    alerts: list[Alert] = []
    alert_vehicle_ids: list[str] = []

    for event in events:
        try:
            row, alert, alert_vehicle_id = build_telemetry_record(event, now)
            rows.append(row)
            if alert is not None:
                alerts.append(alert)
            if alert_vehicle_id is not None:
                alert_vehicle_ids.append(alert_vehicle_id)
        except Exception:
            log.exception(
                "failed to build telemetry row vehicle=%s experiment=%s",
                event.get("vehicle", {}).get("id"),
                event.get("experimentId"),
            )

    if not rows:
        return 0

    with SessionLocal() as db:
        db.add_all(rows)
        if alerts:
            db.add_all(alerts)
        db.commit()

    for vehicle_id in alert_vehicle_ids:
        last_alert_at[vehicle_id] = now

    return len(rows)


def persist_failure(event: dict) -> None:
    vehicle = event["vehicle"]
    ts = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))

    with SessionLocal() as db:
        experiment_id = event.get("experimentId")
        existing = db.execute(
            select(FailureEvent).where(
                FailureEvent.experiment_id == experiment_id,
                FailureEvent.vehicle_id == vehicle["id"],
            )
        ).scalar_one_or_none()

        if existing is not None:
            new_mileage = float(vehicle["mileage"])

            if (
                abs(new_mileage - float(existing.failure_mileage)) <= 0.05
                and existing.component == event["component"]
                and existing.failure_mode == event["failureMode"]
            ):
                return

            if ts <= existing.occurred_at:
                return

            existing.occurred_at = ts
            existing.model = vehicle["model"]
            existing.factory = vehicle["factory"]
            existing.firmware = vehicle["firmware"]
            existing.component = event["component"]
            existing.failure_mode = event["failureMode"]
            existing.pump_revision = vehicle["pumpRevision"]
            existing.failure_mileage = float(vehicle["mileage"])
            existing.fault_code = event["faultCode"]
            existing.simulation_time_acceleration = float(
                event.get("simulationTimeAcceleration", 600.0)
            )
            db.commit()

            log.info(
                "refreshed failure truth experiment=%s vehicle=%s component=%s mode=%s at %.1f mi",
                event.get("experimentId"),
                vehicle["id"],
                event["component"],
                event["failureMode"],
                float(vehicle["mileage"]),
            )
            return

        db.add(
            FailureEvent(
                occurred_at=ts,
                experiment_id=event.get("experimentId"),
                vehicle_id=vehicle["id"],
                model=vehicle["model"],
                factory=vehicle["factory"],
                firmware=vehicle["firmware"],
                component=event["component"],
                failure_mode=event["failureMode"],
                pump_revision=vehicle["pumpRevision"],
                failure_mileage=float(vehicle["mileage"]),
                fault_code=event["faultCode"],
                simulation_time_acceleration=float(
                    event.get("simulationTimeAcceleration", 600.0)
                ),
            )
        )
        db.commit()

        log.info(
            "recorded failure experiment=%s vehicle=%s component=%s mode=%s at %.1f mi",
            event.get("experimentId"),
            vehicle["id"],
            event["component"],
            event["failureMode"],
            float(vehicle["mileage"]),
        )


def main() -> None:
    wait_for_db()

    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            "group.id": "fleetmind-reliability-worker-v2",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )
    consumer.subscribe([TELEMETRY_TOPIC, FAILURE_TOPIC])

    log.info(
        "consuming telemetry=%s failure_truth=%s from %s batch_size=%s batch_timeout=%.2fs",
        TELEMETRY_TOPIC,
        FAILURE_TOPIC,
        KAFKA_BOOTSTRAP_SERVERS,
        WORKER_BATCH_SIZE,
        WORKER_BATCH_TIMEOUT_SECONDS,
    )

    processed_telemetry = 0
    processed_failures = 0
    last_stats_at = time.time()

    try:
        while True:
            messages = consumer.consume(
                num_messages=WORKER_BATCH_SIZE,
                timeout=WORKER_BATCH_TIMEOUT_SECONDS,
            )
            if not messages:
                continue

            telemetry_events: list[dict] = []
            failure_events: list[dict] = []

            for msg in messages:
                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        log.error("kafka error: %s", msg.error())
                    continue

                try:
                    event = json.loads(msg.value().decode("utf-8"))
                except Exception:
                    log.exception("failed to decode message from %s", msg.topic())
                    continue

                if msg.topic() == FAILURE_TOPIC or event.get("eventType") == "component_failure":
                    failure_events.append(event)
                else:
                    telemetry_events.append(event)

            try:
                processed_telemetry += persist_telemetry_batch(telemetry_events)
            except Exception:
                log.exception(
                    "failed telemetry batch size=%s",
                    len(telemetry_events),
                )

            for event in failure_events:
                try:
                    persist_failure(event)
                    processed_failures += 1
                except Exception:
                    log.exception(
                        "failed to persist failure vehicle=%s experiment=%s",
                        event.get("vehicle", {}).get("id"),
                        event.get("experimentId"),
                    )

            now = time.time()
            if now - last_stats_at >= WORKER_STATS_INTERVAL_SECONDS:
                log.info(
                    "worker throughput telemetry=%s failures=%s last_batch=%s",
                    processed_telemetry,
                    processed_failures,
                    len(messages),
                )
                processed_telemetry = 0
                processed_failures = 0
                last_stats_at = now

    finally:
        consumer.close()


if __name__ == "__main__":
    main()
