from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from uuid import uuid4

from confluent_kafka import Producer
from .sim import build_fleet, sample_step

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
TOPIC = os.getenv("TELEMETRY_TOPIC", "vehicle.telemetry.v1")
FAILURE_TOPIC = os.getenv("FAILURE_TOPIC", "vehicle.failure-events.v1")
VEHICLE_COUNT = int(os.getenv("SIMULATED_VEHICLES", "500"))
EVENTS_PER_SECOND = int(os.getenv("SIM_EVENTS_PER_SECOND", "120"))
SEED = int(os.getenv("SIM_SEED", "20260824"))
TIME_ACCELERATION = float(os.getenv("SIM_TIME_ACCELERATION", "600"))
EXPERIMENT_ID = os.getenv("SIM_EXPERIMENT_ID") or f"exp-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def publish(producer: Producer, topic: str, key: str, event: dict) -> None:
    producer.produce(
        topic,
        key=key.encode(),
        value=json.dumps(event, separators=(",", ":")).encode(),
    )
    producer.poll(0)


def main() -> None:
    fleet = build_fleet(VEHICLE_COUNT, SEED)
    rng = random.Random(SEED + 1)
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "linger.ms": 20, "batch.num.messages": 10000})
    print(
        f"FleetMind simulator: {len(fleet)} vehicles -> {TOPIC} @ {EVENTS_PER_SECOND} events/s; "
        f"ground truth -> {FAILURE_TOPIC}; time acceleration={TIME_ACCELERATION:g}x; experiment={EXPERIMENT_ID}",
        flush=True,
    )

    tick = 0
    next_flush = time.time() + 2
    try:
        while True:
            started = time.time()
            for offset in range(EVENTS_PER_SECOND):
                vehicle = fleet[(tick + offset) % len(fleet)]
                step = sample_step(vehicle, tick, VEHICLE_COUNT, EVENTS_PER_SECOND, rng, TIME_ACCELERATION)
                step.telemetry["experimentId"] = EXPERIMENT_ID
                publish(producer, TOPIC, vehicle.id, step.telemetry)
                if step.failure_event is not None:
                    step.failure_event["experimentId"] = EXPERIMENT_ID
                    publish(producer, FAILURE_TOPIC, vehicle.id, step.failure_event)
                    print(
                        f"ground-truth failure: {vehicle.id} "
                        f"{step.failure_event['component']}/{step.failure_event['failureMode']} "
                        f"at {step.failure_event['vehicle']['mileage']} mi",
                        flush=True,
                    )
            tick += EVENTS_PER_SECOND
            if time.time() >= next_flush:
                producer.flush(0.2)
                next_flush = time.time() + 2
            elapsed = time.time() - started
            if elapsed < 1:
                time.sleep(1 - elapsed)
    except KeyboardInterrupt:
        pass
    finally:
        producer.flush(5)


if __name__ == "__main__":
    main()
