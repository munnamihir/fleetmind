from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Vehicle:
    id: str
    model: str
    factory: str
    firmware: str
    pump_revision: str
    mileage: float
    phase: float
    ambient_base: float
    latent_degradation: float
    failure_threshold: float = 1.1
    failure_emitted: bool = False
    initial_mileage: float | None = None

    def __post_init__(self) -> None:
        if self.initial_mileage is None:
            self.initial_mileage = self.mileage


@dataclass(frozen=True)
class SimulationStep:
    telemetry: dict
    failure_event: dict | None


def build_fleet(vehicle_count: int, seed: int = 20260824) -> list[Vehicle]:
    rng = random.Random(seed)
    fleet: list[Vehicle] = []
    models = ["S3", "SY", "SX", "CT"]
    factories = ["Fremont", "Austin", "Berlin"]
    firmware = ["2026.28.7", "2026.32.1", "2026.32.4"]

    for i in range(vehicle_count):
        pump_revision = "CP-17" if rng.random() < 0.12 else rng.choice(["CP-15", "CP-16"])
        ambient = rng.uniform(16, 39)
        mileage = rng.uniform(800, 85000)
        fw = rng.choices(firmware, weights=[0.25, 0.42, 0.33], k=1)[0]

        base_degradation = 0.0
        failure_threshold = 1.1
        if pump_revision == "CP-17":
            mileage_factor = max(0.0, min(1.0, (mileage - 18000) / 36000))
            heat_factor = max(0.0, min(1.0, (ambient - 27) / 12))
            fw_factor = 0.12 if fw == "2026.32.4" else 0.0
            base_degradation = min(1.0, 0.08 + 0.58 * mileage_factor + 0.34 * heat_factor + fw_factor)
            # Unit-to-unit variation produces a distribution of field lifetimes.
            failure_threshold = rng.uniform(0.93, 0.995)

        fleet.append(
            Vehicle(
                id=f"EV-{i + 1:06d}",
                model=rng.choice(models),
                factory=rng.choice(factories),
                firmware=fw,
                pump_revision=pump_revision,
                mileage=mileage,
                phase=rng.random() * math.tau,
                ambient_base=ambient,
                latent_degradation=base_degradation,
                failure_threshold=failure_threshold,
            )
        )
    return fleet


def _sample_internal(
    vehicle: Vehicle,
    tick: int,
    vehicle_count: int,
    events_per_second: int,
    rng: random.Random | None = None,
    time_acceleration: float = 600.0,
) -> tuple[dict, float]:
    rng = rng or random
    road_wave = math.sin(vehicle.phase + tick / 14)
    ambient = vehicle.ambient_base + 2.0 * math.sin(vehicle.phase + tick / 90) + rng.gauss(0, 0.35)
    speed = max(0.0, 46 + 26 * road_wave + rng.gauss(0, 5))
    load = min(1.0, max(0.05, speed / 78))

    # Advance odometer using accelerated fleet time. The scale makes it possible
    # to observe months of field-life behavior during a short engineering demo.
    simulated_seconds_since_sample = max(1.0, vehicle_count / max(events_per_second, 1)) * time_acceleration
    vehicle.mileage += max(0.001, speed / 3600 * simulated_seconds_since_sample)
    driven_miles = max(0.0, vehicle.mileage - float(vehicle.initial_mileage or vehicle.mileage))

    if vehicle.pump_revision == "CP-17":
        progression = min(1.0, vehicle.latent_degradation + 0.35 * driven_miles / 12000.0)
    else:
        progression = min(1.0, vehicle.latent_degradation + 0.02 * driven_miles / 100000.0)

    heat_stress = max(0.0, (ambient - 29) / 12)
    degradation = min(1.0, progression * (0.72 + 0.40 * heat_stress))

    pump_current = 3.05 + 1.85 * degradation + 0.08 * load + rng.gauss(0, 0.07)
    pump_rpm = 2680 - 720 * degradation + rng.gauss(0, 38)
    coolant_temp = 42 + 10.5 * degradation + 0.11 * max(0, ambient - 24) + rng.gauss(0, 0.7)
    battery_temp = 33 + 8.5 * degradation + 0.12 * max(0, ambient - 24) + 2.3 * load + rng.gauss(0, 0.65)

    cell_imbalance = max(0.006, 0.012 + 0.013 * max(0, degradation - 0.65) + rng.gauss(0, 0.002))
    pack_current = 18 + 210 * load + rng.gauss(0, 8)
    inverter_temp = 49 + 29 * load + 8 * degradation + rng.gauss(0, 1.1)
    motor_temp = 47 + 33 * load + 5 * degradation + rng.gauss(0, 1.2)
    motor_rpm = speed * 122 + rng.gauss(0, 150)

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return (
        {
            "schemaVersion": 1,
            "timestamp": timestamp,
            "vehicle": {
                "id": vehicle.id,
                "model": vehicle.model,
                "factory": vehicle.factory,
                "firmware": vehicle.firmware,
                "pumpRevision": vehicle.pump_revision,
                "mileage": round(vehicle.mileage, 1),
            },
            "ambientTempC": round(ambient, 2),
            "speedMph": round(speed, 2),
            "battery": {
                "socPct": round(max(8, min(96, 72 - (tick % 1200) * 0.035 + rng.gauss(0, 0.5))), 2),
                "packVoltageV": round(397 - 0.18 * (tick % 300) + rng.gauss(0, 1.2), 2),
                "packCurrentA": round(pack_current, 2),
                "temperatureC": round(battery_temp, 2),
                "cellImbalanceV": round(cell_imbalance, 4),
            },
            "powertrain": {
                "motorTempC": round(motor_temp, 2),
                "inverterTempC": round(inverter_temp, 2),
                "motorRPM": round(max(0, motor_rpm), 0),
            },
            "thermal": {
                "coolantTempC": round(coolant_temp, 2),
                "pumpRPM": round(max(900, pump_rpm), 0),
                "pumpCurrentA": round(pump_current, 3),
            },
        },
        degradation,
    )


def sample(
    vehicle: Vehicle,
    tick: int,
    vehicle_count: int,
    events_per_second: int,
    rng: random.Random | None = None,
    time_acceleration: float = 600.0,
) -> dict:
    """Public telemetry contract. Ground-truth failure state is never included."""

    telemetry, _ = _sample_internal(vehicle, tick, vehicle_count, events_per_second, rng, time_acceleration)
    return telemetry


def sample_step(
    vehicle: Vehicle,
    tick: int,
    vehicle_count: int,
    events_per_second: int,
    rng: random.Random | None = None,
    time_acceleration: float = 600.0,
) -> SimulationStep:
    """Generate telemetry plus a private ground-truth failure event when due."""

    telemetry, degradation = _sample_internal(vehicle, tick, vehicle_count, events_per_second, rng, time_acceleration)
    failure_event = None

    if (
        vehicle.pump_revision == "CP-17"
        and not vehicle.failure_emitted
        and degradation >= vehicle.failure_threshold
    ):
        vehicle.failure_emitted = True
        failure_event = {
            "schemaVersion": 1,
            "eventType": "component_failure",
            "timestamp": telemetry["timestamp"],
            "vehicle": telemetry["vehicle"],
            "component": "coolant_pump",
            "failureMode": "bearing_friction_thermal_loss",
            "faultCode": "FM-PUMP-001",
            "simulationTimeAcceleration": time_acceleration,
        }

    return SimulationStep(telemetry=telemetry, failure_event=failure_event)
