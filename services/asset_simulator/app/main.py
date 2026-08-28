from __future__ import annotations

import json
import math
import os
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from confluent_kafka import Producer


KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "redpanda:9092",
)
ASSET_TELEMETRY_TOPIC = os.getenv(
    "ASSET_TELEMETRY_TOPIC",
    "asset.telemetry.v1",
)
ASSET_COUNT = max(
    3,
    int(os.getenv(
        "ASSET_SIMULATED_ASSETS",
        "90",
    )),
)
EVENTS_PER_SECOND = max(
    1,
    int(os.getenv(
        "ASSET_SIM_EVENTS_PER_SECOND",
        "30",
    )),
)
SEED = int(
    os.getenv("ASSET_SIM_SEED", "20260827")
)
EXPERIMENT_ID = os.getenv(
    "ASSET_EXPERIMENT_ID",
    f"asset-{int(time.time())}",
)


@dataclass
class Asset:
    asset_id: str
    asset_type: str
    model: str
    site: str
    firmware: str
    phase: float
    latent_degradation: float
    degrading: bool


def build_assets(
    count: int,
    seed: int,
) -> list[Asset]:
    rng = random.Random(seed)
    asset_types = (
        "robot",
        "charger",
        "energy_system",
    )
    models = {
        "robot": (
            "RBT-A",
            "RBT-B",
        ),
        "charger": (
            "DC-250",
            "DC-350",
        ),
        "energy_system": (
            "ESS-1",
            "ESS-2",
        ),
    }

    assets = []
    for index in range(count):
        asset_type = asset_types[
            index % len(asset_types)
        ]
        degrading = (
            rng.random() < 0.28
        )
        assets.append(
            Asset(
                asset_id=(
                    f"{asset_type[:3].upper()}-"
                    f"{index + 1:05d}"
                ),
                asset_type=asset_type,
                model=rng.choice(
                    models[asset_type]
                ),
                site=rng.choice(
                    (
                        "Austin",
                        "Fremont",
                        "Berlin",
                        "Nevada",
                    )
                ),
                firmware=rng.choice(
                    (
                        "9.5.0",
                        "9.5.1",
                        "9.6.0",
                    )
                ),
                phase=(
                    rng.random()
                    * math.tau
                ),
                latent_degradation=(
                    rng.uniform(
                        0.05,
                        0.35,
                    )
                    if degrading
                    else 0.0
                ),
                degrading=degrading,
            )
        )
    return assets


def _degradation(
    asset: Asset,
    tick: int,
) -> float:
    if not asset.degrading:
        return 0.0

    return min(
        1.0,
        asset.latent_degradation
        + tick / 25000.0,
    )


def _robot_metrics(
    asset: Asset,
    tick: int,
    rng: random.Random,
) -> dict:
    severity = _degradation(
        asset,
        tick,
    )
    load = (
        0.55
        + 0.35
        * math.sin(
            asset.phase
            + tick / 22.0
        )
    )
    load = max(
        0.05,
        min(1.0, load),
    )

    return {
        "actuator_current_a": round(
            10.5
            + 8.5 * load
            + 8.5 * severity
            + rng.gauss(0, 0.5),
            4,
        ),
        "actuator_temp_c": round(
            48.0
            + 20.0 * load
            + 28.0 * severity
            + rng.gauss(0, 0.8),
            4,
        ),
        "actuator_torque_nm": round(
            55.0
            + 75.0 * load
            + rng.gauss(0, 2.5),
            4,
        ),
        "gearbox_vibration_rms": round(
            1.2
            + 1.8 * load
            + 6.5 * severity
            + abs(rng.gauss(0, 0.25)),
            4,
        ),
        "gearbox_temp_c": round(
            42.0
            + 22.0 * load
            + 30.0 * severity
            + rng.gauss(0, 0.9),
            4,
        ),
    }


def _charger_metrics(
    asset: Asset,
    tick: int,
    rng: random.Random,
) -> dict:
    severity = _degradation(
        asset,
        tick,
    )
    load = (
        0.55
        + 0.35
        * math.sin(
            asset.phase
            + tick / 28.0
        )
    )
    load = max(
        0.08,
        min(1.0, load),
    )

    return {
        "output_kw": round(
            65.0
            + 250.0 * load,
            4,
        ),
        "connector_temp_c": round(
            34.0
            + 28.0 * load
            + 24.0 * severity
            + rng.gauss(0, 0.7),
            4,
        ),
        "coolant_temp_c": round(
            30.0
            + 19.0 * load
            + 23.0 * severity
            + rng.gauss(0, 0.6),
            4,
        ),
        "fan_current_a": round(
            2.2
            + 1.7 * load
            + 2.8 * severity
            + rng.gauss(0, 0.08),
            4,
        ),
        "efficiency_pct": round(
            96.7
            - 1.4 * load
            - 4.0 * severity
            + rng.gauss(0, 0.08),
            4,
        ),
        "voltage_ripple_pct": round(
            0.7
            + 0.8 * load
            + 3.5 * severity
            + abs(rng.gauss(0, 0.08)),
            4,
        ),
    }


def _energy_metrics(
    asset: Asset,
    tick: int,
    rng: random.Random,
) -> dict:
    severity = _degradation(
        asset,
        tick,
    )
    load = (
        0.52
        + 0.38
        * math.sin(
            asset.phase
            + tick / 35.0
        )
    )
    load = max(
        0.05,
        min(1.0, load),
    )

    return {
        "power_kw": round(
            120.0
            + 700.0 * load,
            4,
        ),
        "inverter_temp_c": round(
            42.0
            + 28.0 * load
            + 25.0 * severity
            + rng.gauss(0, 0.7),
            4,
        ),
        "module_imbalance_v": round(
            0.018
            + 0.025 * load
            + 0.13 * severity
            + abs(rng.gauss(0, 0.003)),
            5,
        ),
        "cooling_current_a": round(
            3.1
            + 2.1 * load
            + 4.5 * severity
            + rng.gauss(0, 0.12),
            4,
        ),
        "soc_pct": round(
            20.0
            + 68.0
            * (
                0.5
                + 0.5
                * math.sin(
                    asset.phase
                    + tick / 140.0
                )
            ),
            4,
        ),
    }


def build_event(
    asset: Asset,
    tick: int,
    rng: random.Random,
) -> dict:
    if asset.asset_type == "robot":
        metrics = _robot_metrics(
            asset,
            tick,
            rng,
        )
    elif asset.asset_type == "charger":
        metrics = _charger_metrics(
            asset,
            tick,
            rng,
        )
    else:
        metrics = _energy_metrics(
            asset,
            tick,
            rng,
        )

    return {
        "eventId": uuid.uuid4().hex,
        "timestamp": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "experimentId": (
            EXPERIMENT_ID
        ),
        "assetId": asset.asset_id,
        "assetType": asset.asset_type,
        "context": {
            "model": asset.model,
            "site": asset.site,
            "firmware": asset.firmware,
        },
        "metrics": metrics,
    }


def main() -> None:
    rng = random.Random(SEED)
    assets = build_assets(
        ASSET_COUNT,
        SEED,
    )
    producer = Producer(
        {
            "bootstrap.servers": (
                KAFKA_BOOTSTRAP_SERVERS
            ),
            "linger.ms": 20,
            "batch.num.messages": 1000,
        }
    )

    print(
        "FleetMind multi-asset simulator "
        f"experiment={EXPERIMENT_ID} "
        f"assets={len(assets)} "
        f"rate={EVENTS_PER_SECOND}/s",
        flush=True,
    )

    tick = 0
    interval = (
        1.0 / EVENTS_PER_SECOND
    )
    next_emit = time.perf_counter()

    try:
        while True:
            asset = assets[
                tick % len(assets)
            ]
            event = build_event(
                asset,
                tick,
                rng,
            )
            producer.produce(
                ASSET_TELEMETRY_TOPIC,
                key=asset.asset_id,
                value=json.dumps(
                    event,
                    separators=(",", ":"),
                ),
            )

            tick += 1
            if tick % 1000 == 0:
                producer.poll(0)

            next_emit += interval
            delay = (
                next_emit
                - time.perf_counter()
            )
            if delay > 0:
                time.sleep(delay)
            else:
                next_emit = (
                    time.perf_counter()
                )
    finally:
        producer.flush(10)


if __name__ == "__main__":
    main()
