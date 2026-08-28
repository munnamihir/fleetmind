#!/usr/bin/env python3
"""FleetMind Kafka load generator for Phase 9.2.

This tool targets broker/ingestion throughput. A target such as 100000 events/s
is a requested load, not a claimed achieved result. The script prints measured
producer throughput from the local run.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
import uuid
from datetime import datetime, timezone

from confluent_kafka import Producer


def vehicle_event(
    index: int,
    tick: int,
    rng: random.Random,
    experiment_id: str,
) -> dict:
    phase = (index % 100) / 100.0 * math.tau
    load = 0.5 + 0.4 * math.sin(phase + tick / 30.0)
    ambient = 24.0 + 8.0 * math.sin(phase + tick / 90.0)
    pump_current = 3.05 + 0.15 * load + rng.gauss(0, 0.03)
    pump_rpm = 2680.0 - 55.0 * load + rng.gauss(0, 20.0)
    coolant = 41.0 + 3.0 * load + 0.15 * max(0.0, ambient - 23.0)
    battery_temp = 31.0 + 4.5 * load + 0.12 * max(0.0, ambient - 23.0)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experimentId": experiment_id,
        "vehicle": {
            "id": f"LOAD-EV-{index:07d}",
            "model": "LOAD",
            "factory": "LoadLab",
            "firmware": "load-9.2",
            "pumpRevision": "LOAD",
            "mileage": float(10000 + tick / 10.0 + index),
        },
        "ambientTempC": round(ambient, 4),
        "speedMph": round(45.0 + 20.0 * load, 4),
        "battery": {
            "socPct": round(75.0 - (tick % 500) / 20.0, 4),
            "packVoltageV": 390.0,
            "packCurrentA": round(50.0 + 90.0 * load, 4),
            "temperatureC": round(battery_temp, 4),
            "cellImbalanceV": round(0.015 + 0.01 * load, 5),
        },
        "powertrain": {
            "motorTempC": round(50.0 + 20.0 * load, 4),
            "inverterTempC": round(48.0 + 18.0 * load, 4),
            "motorRPM": round(2200.0 + 4500.0 * load, 4),
        },
        "thermal": {
            "coolantTempC": round(coolant, 4),
            "pumpRPM": round(pump_rpm, 4),
            "pumpCurrentA": round(pump_current, 4),
        },
    }


def asset_event(
    index: int,
    tick: int,
    experiment_id: str,
) -> dict:
    return {
        "eventId": uuid.uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experimentId": experiment_id,
        "assetId": f"LOAD-RBT-{index:07d}",
        "assetType": "robot",
        "context": {
            "model": "LOAD-RBT",
            "site": "LoadLab",
            "firmware": "load-9.5",
        },
        "metrics": {
            "actuator_current_a": 12.0 + (tick % 30) / 10.0,
            "actuator_temp_c": 55.0 + (tick % 40) / 4.0,
            "actuator_torque_nm": 80.0 + (tick % 50),
            "gearbox_vibration_rms": 1.5 + (tick % 20) / 10.0,
            "gearbox_temp_c": 52.0 + (tick % 30) / 3.0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brokers", default="localhost:19092")
    parser.add_argument("--topic", default="vehicle.telemetry.v1")
    parser.add_argument(
        "--mode",
        choices=("vehicle", "asset", "broker"),
        default="broker",
    )
    parser.add_argument("--rate", type=int, default=100000)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--vehicles", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=92026)
    parser.add_argument("--report-every", type=float, default=2.0)
    args = parser.parse_args()

    target_rate = max(1, args.rate)
    duration = max(0.1, args.duration)
    rng = random.Random(args.seed)
    experiment_id = f"load-{int(time.time())}"

    producer = Producer(
        {
            "bootstrap.servers": args.brokers,
            "linger.ms": 5,
            "batch.num.messages": 10000,
            "queue.buffering.max.messages": 1000000,
            "queue.buffering.max.kbytes": 1048576,
            "compression.type": "lz4",
        }
    )

    started = time.perf_counter()
    report_at = started + max(0.25, args.report_every)
    deadline = started + duration
    sent = 0
    delivered = 0
    failed = 0

    def delivery(error, message):
        nonlocal delivered, failed
        if error is None:
            delivered += 1
        else:
            failed += 1

    batch_interval = 0.01
    per_batch = max(1, int(target_rate * batch_interval))
    next_batch = started

    while time.perf_counter() < deadline:
        now = time.perf_counter()

        if now < next_batch:
            producer.poll(0)
            time.sleep(min(0.001, next_batch - now))
            continue

        for _ in range(per_batch):
            index = sent % max(1, args.vehicles)
            if args.mode == "vehicle":
                payload = vehicle_event(index, sent, rng, experiment_id)
                value = json.dumps(payload, separators=(",", ":"))
                key = payload["vehicle"]["id"]
            elif args.mode == "asset":
                payload = asset_event(index, sent, experiment_id)
                value = json.dumps(payload, separators=(",", ":"))
                key = payload["assetId"]
            else:
                value = json.dumps(
                    {
                        "eventId": sent,
                        "experimentId": experiment_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": "x" * 256,
                    },
                    separators=(",", ":"),
                )
                key = str(index)

            while True:
                try:
                    producer.produce(
                        args.topic,
                        key=key,
                        value=value,
                        on_delivery=delivery,
                    )
                    break
                except BufferError:
                    producer.poll(0.01)

            sent += 1

        producer.poll(0)
        next_batch += batch_interval

        if now >= report_at:
            elapsed = now - started
            print(
                f"elapsed={elapsed:.2f}s sent={sent:,} "
                f"accepted_rate={sent / max(elapsed, 1e-9):,.0f}/s "
                f"delivered={delivered:,} failed={failed:,}",
                flush=True,
            )
            report_at = now + max(0.25, args.report_every)

        if now - next_batch > 0.5:
            next_batch = now

    producer.flush(30)
    elapsed = time.perf_counter() - started

    print(
        json.dumps(
            {
                "requestedRatePerSecond": target_rate,
                "durationSeconds": round(elapsed, 4),
                "sent": sent,
                "delivered": delivered,
                "failed": failed,
                "acceptedRatePerSecond": round(sent / max(elapsed, 1e-9), 2),
                "deliveredRatePerSecond": round(
                    delivered / max(elapsed, 1e-9), 2
                ),
                "targetAchievedByDeliveredRate": (
                    delivered / max(elapsed, 1e-9) >= target_rate
                ),
                "note": (
                    "A true platform capacity claim also requires broker, worker, "
                    "database, latency, lag and recovery observations."
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
