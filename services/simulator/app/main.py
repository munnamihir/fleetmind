from __future__ import annotations

import json
import os
import random
import time

from confluent_kafka import Producer
from .sim import build_fleet, sample

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
TOPIC = os.getenv("TELEMETRY_TOPIC", "vehicle.telemetry.v1")
VEHICLE_COUNT = int(os.getenv("SIMULATED_VEHICLES", "500"))
EVENTS_PER_SECOND = int(os.getenv("SIM_EVENTS_PER_SECOND", "120"))
SEED = int(os.getenv("SIM_SEED", "20260824"))


def main() -> None:
    fleet = build_fleet(VEHICLE_COUNT, SEED)
    rng = random.Random(SEED + 1)
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "linger.ms": 20, "batch.num.messages": 10000})
    print(f"FleetMind simulator: {len(fleet)} vehicles -> {TOPIC} @ {EVENTS_PER_SECOND} events/s")

    tick = 0
    next_flush = time.time() + 2
    try:
        while True:
            started = time.time()
            for offset in range(EVENTS_PER_SECOND):
                vehicle = fleet[(tick + offset) % len(fleet)]
                event = sample(vehicle, tick, VEHICLE_COUNT, EVENTS_PER_SECOND, rng)
                producer.produce(
                    TOPIC,
                    key=vehicle.id.encode(),
                    value=json.dumps(event, separators=(",", ":")).encode(),
                )
                producer.poll(0)
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
