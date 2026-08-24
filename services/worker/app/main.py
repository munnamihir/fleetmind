from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaError
from sqlalchemy import select

from fleetmind_common.config import FAILURE_TOPIC, KAFKA_BOOTSTRAP_SERVERS, TELEMETRY_TOPIC
from fleetmind_common.db import Base, SessionLocal, engine
from fleetmind_common.models import Alert, FailureEvent, Telemetry
from fleetmind_common.risk import score_telemetry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fleetmind-worker")

last_alert_at: dict[str, float] = {}
ALERT_COOLDOWN_SECONDS = 25


def wait_for_db() -> None:
    for attempt in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:
            log.warning("database not ready (%s/30): %s", attempt + 1, exc)
            time.sleep(2)
    raise RuntimeError("database unavailable")


def persist_telemetry(event: dict) -> None:
    risk = score_telemetry(event)
    battery = event["battery"]
    powertrain = event["powertrain"]
    thermal = event["thermal"]
    vehicle = event["vehicle"]

    ts = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    row = Telemetry(
        timestamp=ts,
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

    now = time.time()
    should_alert = (
        risk.status != "healthy"
        and now - last_alert_at.get(vehicle["id"], 0) >= ALERT_COOLDOWN_SECONDS
    )

    with SessionLocal() as db:
        db.add(row)
        if should_alert:
            db.add(
                Alert(
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
            )
            last_alert_at[vehicle["id"]] = now
        db.commit()


def persist_failure(event: dict) -> None:
    vehicle = event["vehicle"]
    ts = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))

    with SessionLocal() as db:
        existing = db.execute(
            select(FailureEvent).where(FailureEvent.vehicle_id == vehicle["id"])
        ).scalar_one_or_none()
        if existing is not None:
            return

        db.add(
            FailureEvent(
                occurred_at=ts,
                vehicle_id=vehicle["id"],
                model=vehicle["model"],
                factory=vehicle["factory"],
                firmware=vehicle["firmware"],
                component=event["component"],
                failure_mode=event["failureMode"],
                pump_revision=vehicle["pumpRevision"],
                failure_mileage=float(vehicle["mileage"]),
                fault_code=event["faultCode"],
                simulation_time_acceleration=float(event.get("simulationTimeAcceleration", 600.0)),
            )
        )
        db.commit()
        log.info(
            "recorded failure %s %s at %.1f mi",
            vehicle["id"],
            vehicle["pumpRevision"],
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
        "consuming telemetry=%s failure_truth=%s from %s",
        TELEMETRY_TOPIC,
        FAILURE_TOPIC,
        KAFKA_BOOTSTRAP_SERVERS,
    )

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.error("kafka error: %s", msg.error())
                continue
            try:
                event = json.loads(msg.value().decode("utf-8"))
                if msg.topic() == FAILURE_TOPIC or event.get("eventType") == "component_failure":
                    persist_failure(event)
                else:
                    persist_telemetry(event)
            except Exception:
                log.exception("failed to process message from %s", msg.topic())
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
