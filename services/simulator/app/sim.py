from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone


MIN_FAILURE_OBSERVATION_MILES = 3000.0

FAULT_HEALTHY = "healthy"
FAULT_COOLANT_PUMP = "coolant_pump"
FAULT_BATTERY_IMBALANCE = "battery_cell_imbalance"
FAULT_INVERTER_COOLING = "inverter_cooling"
FAULT_MOTOR_THERMAL = "motor_thermal"
FAULT_COOLANT_SENSOR = "coolant_sensor_drift"

FAULT_FAMILIES = (
    FAULT_HEALTHY,
    FAULT_COOLANT_PUMP,
    FAULT_BATTERY_IMBALANCE,
    FAULT_INVERTER_COOLING,
    FAULT_MOTOR_THERMAL,
    FAULT_COOLANT_SENSOR,
)

FAULT_EVENT_DEFINITIONS = {
    FAULT_COOLANT_PUMP: {
        "component": "coolant_pump",
        "failureMode": "bearing_friction_thermal_loss",
        "faultCode": "FM-PUMP-001",
    },
    FAULT_BATTERY_IMBALANCE: {
        "component": "battery_pack",
        "failureMode": "cell_imbalance_growth",
        "faultCode": "FM-BATT-001",
    },
    FAULT_INVERTER_COOLING: {
        "component": "inverter",
        "failureMode": "cooling_efficiency_loss",
        "faultCode": "FM-INV-001",
    },
    FAULT_MOTOR_THERMAL: {
        "component": "traction_motor",
        "failureMode": "winding_thermal_resistance",
        "faultCode": "FM-MOTOR-001",
    },
    FAULT_COOLANT_SENSOR: {
        "component": "coolant_temp_sensor",
        "failureMode": "positive_bias_drift",
        "faultCode": "FM-SENSOR-001",
    },
}


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
    fault_family: str | None = None
    operating_profile: str = "normal"

    def __post_init__(self) -> None:
        if self.initial_mileage is None:
            self.initial_mileage = self.mileage
        # Backward compatibility for the Phase 1-5 unit tests and hand-built
        # CP-17 vehicles. build_fleet() always sets the fault family explicitly.
        if self.fault_family is None:
            self.fault_family = (
                FAULT_COOLANT_PUMP
                if self.pump_revision == "CP-17" and self.latent_degradation > 0
                else FAULT_HEALTHY
            )


@dataclass(frozen=True)
class SimulationStep:
    telemetry: dict
    failure_event: dict | None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


def _choose_fault_family(rng: random.Random) -> str:
    # Synthetic portfolio distribution only; these are not field failure rates.
    draw = rng.random()
    if draw < 0.50:
        return FAULT_HEALTHY
    if draw < 0.64:
        return FAULT_COOLANT_PUMP
    if draw < 0.74:
        return FAULT_BATTERY_IMBALANCE
    if draw < 0.83:
        return FAULT_INVERTER_COOLING
    if draw < 0.91:
        return FAULT_MOTOR_THERMAL
    return FAULT_COOLANT_SENSOR


def _choose_operating_profile(rng: random.Random) -> str:
    draw = rng.random()
    if draw < 0.12:
        return "hot_climate"
    if draw < 0.24:
        return "high_load"
    return "normal"


def _initial_fault_state(
    fault_family: str,
    mileage: float,
    ambient: float,
    firmware: str,
    rng: random.Random,
) -> tuple[float, float]:
    if fault_family == FAULT_HEALTHY:
        return 0.0, 1.1

    age_factor = _clamp((mileage - 12000.0) / 68000.0)
    heat_factor = _clamp((ambient - 27.0) / 14.0)

    if fault_family == FAULT_COOLANT_PUMP:
        firmware_factor = 0.15 if firmware == "2026.32.4" else 0.0
        initial = 0.05 + 0.34 * age_factor + 0.12 * heat_factor + firmware_factor
        threshold = rng.uniform(0.84, 0.91) if firmware == "2026.32.4" else rng.uniform(0.91, 0.98)
    elif fault_family == FAULT_BATTERY_IMBALANCE:
        initial = 0.06 + 0.31 * age_factor + 0.08 * heat_factor
        threshold = rng.uniform(0.90, 0.98)
    elif fault_family == FAULT_INVERTER_COOLING:
        initial = 0.05 + 0.27 * age_factor + 0.13 * heat_factor
        threshold = rng.uniform(0.88, 0.97)
    elif fault_family == FAULT_MOTOR_THERMAL:
        initial = 0.05 + 0.24 * age_factor + 0.08 * heat_factor
        threshold = rng.uniform(0.90, 0.98)
    elif fault_family == FAULT_COOLANT_SENSOR:
        initial = 0.04 + 0.22 * age_factor
        threshold = rng.uniform(0.88, 0.96)
    else:
        raise ValueError(f"unknown fault family: {fault_family}")

    return min(0.78, initial), threshold


def build_fleet(vehicle_count: int, seed: int = 20260824) -> list[Vehicle]:
    rng = random.Random(seed)
    fleet: list[Vehicle] = []
    models = ["S3", "SY", "SX", "CT"]
    factories = ["Fremont", "Austin", "Berlin"]
    firmware = ["2026.28.7", "2026.32.1", "2026.32.4"]

    for i in range(vehicle_count):
        fault_family = _choose_fault_family(rng)
        operating_profile = _choose_operating_profile(rng)

        # CP-17 remains necessary for the synthetic pump defect, but CP-17 also
        # appears in non-pump cohorts so hardware revision alone is not a label.
        if fault_family == FAULT_COOLANT_PUMP:
            pump_revision = "CP-17"
        else:
            pump_revision = rng.choices(["CP-15", "CP-16", "CP-17"], weights=[0.38, 0.38, 0.24], k=1)[0]

        ambient = rng.uniform(15, 38)
        mileage = rng.uniform(800, 85000)
        fw = rng.choices(firmware, weights=[0.25, 0.42, 0.33], k=1)[0]
        latent_degradation, failure_threshold = _initial_fault_state(
            fault_family, mileage, ambient, fw, rng
        )

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
                latent_degradation=latent_degradation,
                failure_threshold=failure_threshold,
                fault_family=fault_family,
                operating_profile=operating_profile,
            )
        )
    return fleet


def _fault_severity(vehicle: Vehicle, driven_miles: float, ambient: float) -> float:
    family = vehicle.fault_family or FAULT_HEALTHY
    if family == FAULT_HEALTHY:
        return 0.0

    progression_rate = {
        FAULT_COOLANT_PUMP: 0.72 if vehicle.firmware == "2026.32.4" else 0.34,
        FAULT_BATTERY_IMBALANCE: 0.42,
        FAULT_INVERTER_COOLING: 0.48,
        FAULT_MOTOR_THERMAL: 0.40,
        FAULT_COOLANT_SENSOR: 0.52,
    }[family]

    progression = min(
        1.0,
        vehicle.latent_degradation + progression_rate * driven_miles / 12000.0,
    )
    if family == FAULT_COOLANT_SENSOR:
        return progression

    heat_stress = _clamp((ambient - 30.0) / 14.0)
    return min(1.0, progression + 0.08 * heat_stress)


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

    profile_ambient_bias = 6.0 if vehicle.operating_profile == "hot_climate" else 0.0
    ambient = (
        vehicle.ambient_base
        + profile_ambient_bias
        + 2.0 * math.sin(vehicle.phase + tick / 90)
        + rng.gauss(0, 0.35)
    )
    speed = max(0.0, 46 + 26 * road_wave + rng.gauss(0, 5))
    load = speed / 78
    if vehicle.operating_profile == "high_load":
        load += 0.22
    load = _clamp(load, 0.05, 1.0)

    # Advance odometer using accelerated fleet time. The scale makes it possible
    # to observe months of field-life behavior during a short engineering demo.
    simulated_seconds_since_sample = max(1.0, vehicle_count / max(events_per_second, 1)) * time_acceleration
    vehicle.mileage += max(0.001, speed / 3600 * simulated_seconds_since_sample)
    driven_miles = max(0.0, vehicle.mileage - float(vehicle.initial_mileage or vehicle.mileage))
    severity = _fault_severity(vehicle, driven_miles, ambient)

    ambient_excess = max(0.0, ambient - 23.0)

    # Healthy physics + operating-condition confounders.
    pump_current = 3.03 + 0.10 * load + rng.gauss(0, 0.07)
    pump_rpm = 2690 - 45 * load + rng.gauss(0, 38)
    coolant_temp = 40.5 + 0.20 * ambient_excess + 2.3 * load + rng.gauss(0, 0.7)
    battery_temp = 31.5 + 0.17 * ambient_excess + 3.0 * load + rng.gauss(0, 0.65)

    cell_imbalance = max(0.006, 0.012 + rng.gauss(0, 0.002))
    pack_current = 18 + 210 * load + rng.gauss(0, 8)
    pack_voltage = 397 - 0.18 * (tick % 300) + rng.gauss(0, 1.2)
    inverter_temp = 47 + 30 * load + 0.12 * ambient_excess + rng.gauss(0, 1.1)
    motor_temp = 45 + 34 * load + 0.10 * ambient_excess + rng.gauss(0, 1.2)
    motor_rpm = speed * 122 + rng.gauss(0, 150)

    # Fault-specific observable signatures. Hidden family/severity never enters
    # the public event; only physical sensor consequences do.
    family = vehicle.fault_family or FAULT_HEALTHY
    if family == FAULT_COOLANT_PUMP:
        pump_current += 1.85 * severity
        pump_rpm -= 760 * severity
        coolant_temp += 11.0 * severity
        battery_temp += 7.0 * severity
        inverter_temp += 4.0 * severity
    elif family == FAULT_BATTERY_IMBALANCE:
        cell_imbalance += 0.060 * severity
        battery_temp += 10.0 * severity
        pack_voltage -= 11.0 * severity * (0.35 + 0.65 * load)
        pack_current += 6.0 * severity * load
    elif family == FAULT_INVERTER_COOLING:
        inverter_temp += 28.0 * severity * (0.50 + 0.65 * load)
        coolant_temp += 7.0 * severity
        motor_temp += 8.0 * severity
        battery_temp += 3.0 * severity
    elif family == FAULT_MOTOR_THERMAL:
        motor_temp += 30.0 * severity * (0.45 + 0.75 * load)
        inverter_temp += 6.0 * severity
        battery_temp += 3.0 * severity
        pack_current += 18.0 * severity * load
    elif family == FAULT_COOLANT_SENSOR:
        # Sensor bias changes the reported coolant temperature while the
        # corroborating thermal/pump channels remain physically normal.
        coolant_temp += 16.0 * severity

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
                "packVoltageV": round(pack_voltage, 2),
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
        severity,
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

    telemetry, severity = _sample_internal(vehicle, tick, vehicle_count, events_per_second, rng, time_acceleration)
    failure_event = None

    driven_miles = max(0.0, vehicle.mileage - float(vehicle.initial_mileage or vehicle.mileage))
    family = vehicle.fault_family or FAULT_HEALTHY
    definition = FAULT_EVENT_DEFINITIONS.get(family)

    if (
        definition is not None
        and not vehicle.failure_emitted
        and driven_miles >= MIN_FAILURE_OBSERVATION_MILES
        and severity >= vehicle.failure_threshold
    ):
        vehicle.failure_emitted = True
        failure_event = {
            "schemaVersion": 1,
            "eventType": "component_failure",
            "timestamp": telemetry["timestamp"],
            "vehicle": telemetry["vehicle"],
            "component": definition["component"],
            "failureMode": definition["failureMode"],
            "faultCode": definition["faultCode"],
            "simulationTimeAcceleration": time_acceleration,
        }

    return SimulationStep(telemetry=telemetry, failure_event=failure_event)
