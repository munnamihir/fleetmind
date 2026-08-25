import random
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "services" / "common"))
sys.path.insert(0, str(ROOT / "services" / "simulator"))

from fleetmind_common.risk import score_telemetry
from app.sim import (
    FAULT_BATTERY_IMBALANCE,
    FAULT_COOLANT_PUMP,
    FAULT_COOLANT_SENSOR,
    FAULT_FAMILIES,
    FAULT_HEALTHY,
    FAULT_INVERTER_COOLING,
    FAULT_MOTOR_THERMAL,
    Vehicle,
    build_fleet,
    sample,
    sample_step,
)


def vehicle_for_fault(fault_family: str, *, profile: str = "normal") -> Vehicle:
    return Vehicle(
        "EV-T",
        "SY",
        "Austin",
        "2026.32.4",
        "CP-17" if fault_family == FAULT_COOLANT_PUMP else "CP-16",
        60000,
        0.3,
        30,
        0.95 if fault_family != FAULT_HEALTHY else 0.0,
        failure_threshold=0.90,
        initial_mileage=56000,
        fault_family=fault_family,
        operating_profile=profile,
    )


class SimulationTests(unittest.TestCase):
    def test_hidden_degradation_surfaces_as_observable_risk(self):
        healthy = Vehicle("EV-H", "SY", "Austin", "2026.32.4", "CP-16", 45000, 0.3, 36, 0.0)
        degraded = Vehicle("EV-D", "SY", "Austin", "2026.32.4", "CP-17", 45000, 0.3, 36, 0.95)

        healthy_event = sample(healthy, 9000, 500, 120, random.Random(7))
        degraded_event = sample(degraded, 9000, 500, 120, random.Random(7))

        # No internal failure/degradation truth leaks into the telemetry contract.
        self.assertNotIn("latent_degradation", degraded_event)
        self.assertNotIn("failed", degraded_event)

        healthy_risk = score_telemetry(healthy_event)
        degraded_risk = score_telemetry(degraded_event)
        self.assertGreater(degraded_risk.score, healthy_risk.score)
        self.assertGreater(degraded_event["thermal"]["pumpCurrentA"], healthy_event["thermal"]["pumpCurrentA"])
        self.assertLess(degraded_event["thermal"]["pumpRPM"], healthy_event["thermal"]["pumpRPM"])

    def test_failure_truth_is_separate_from_telemetry(self):
        vehicle = Vehicle(
            "EV-F", "SY", "Austin", "2026.32.4", "CP-17", 60000, 0.3, 38, 1.0,
            failure_threshold=0.90,
            initial_mileage=56000,
        )
        step = sample_step(vehicle, 18000, 500, 120, random.Random(8))
        self.assertIsNotNone(step.failure_event)
        self.assertNotIn("eventType", step.telemetry)
        self.assertNotIn("failureMode", step.telemetry)
        self.assertNotIn("failed", step.telemetry)
        self.assertEqual(step.failure_event["eventType"], "component_failure")

        second = sample_step(vehicle, 18120, 500, 120, random.Random(9))
        self.assertIsNone(second.failure_event)

    def test_failure_requires_observation_warmup(self):
        vehicle = Vehicle(
            "EV-W", "SY", "Austin", "2026.32.4", "CP-17", 60000, 0.3, 38, 1.0,
            failure_threshold=0.90,
        )
        step = sample_step(vehicle, 18000, 500, 120, random.Random(8))
        self.assertIsNone(step.failure_event)

    def test_seeded_fleet_contains_all_fault_families_and_healthy_cp17_controls(self):
        fleet = build_fleet(500, seed=20260824)
        counts = Counter(vehicle.fault_family for vehicle in fleet)
        self.assertEqual(set(counts), set(FAULT_FAMILIES))
        self.assertTrue(
            any(
                vehicle.fault_family == FAULT_HEALTHY
                and vehicle.pump_revision == "CP-17"
                for vehicle in fleet
            )
        )

    def test_public_telemetry_never_exposes_fault_family_or_operating_profile(self):
        forbidden = {
            "faultFamily",
            "fault_family",
            "operatingProfile",
            "operating_profile",
            "latent_degradation",
            "failureMode",
            "faultCode",
            "failed",
        }
        for index, family in enumerate(FAULT_FAMILIES):
            event = sample(
                vehicle_for_fault(family, profile="hot_climate"),
                12000,
                500,
                120,
                random.Random(100 + index),
            )
            self.assertTrue(forbidden.isdisjoint(event.keys()))
            self.assertTrue(forbidden.isdisjoint(event["vehicle"].keys()))

    def test_fault_families_create_distinct_but_overlapping_sensor_signatures(self):
        healthy = sample(vehicle_for_fault(FAULT_HEALTHY), 12000, 500, 120, random.Random(21))
        battery = sample(vehicle_for_fault(FAULT_BATTERY_IMBALANCE), 12000, 500, 120, random.Random(21))
        inverter = sample(vehicle_for_fault(FAULT_INVERTER_COOLING), 12000, 500, 120, random.Random(21))
        motor = sample(vehicle_for_fault(FAULT_MOTOR_THERMAL), 12000, 500, 120, random.Random(21))
        sensor = sample(vehicle_for_fault(FAULT_COOLANT_SENSOR), 12000, 500, 120, random.Random(21))

        self.assertGreater(
            battery["battery"]["cellImbalanceV"] - healthy["battery"]["cellImbalanceV"],
            0.04,
        )
        self.assertGreater(
            inverter["powertrain"]["inverterTempC"] - healthy["powertrain"]["inverterTempC"],
            12.0,
        )
        self.assertGreater(
            motor["powertrain"]["motorTempC"] - healthy["powertrain"]["motorTempC"],
            12.0,
        )
        self.assertGreater(
            sensor["thermal"]["coolantTempC"] - healthy["thermal"]["coolantTempC"],
            10.0,
        )
        self.assertLess(
            abs(sensor["thermal"]["pumpCurrentA"] - healthy["thermal"]["pumpCurrentA"]),
            0.01,
        )
        self.assertLess(
            abs(sensor["battery"]["temperatureC"] - healthy["battery"]["temperatureC"]),
            0.01,
        )

    def test_private_failure_truth_maps_each_fault_to_component_and_code(self):
        expected = {
            FAULT_COOLANT_PUMP: ("coolant_pump", "FM-PUMP-001"),
            FAULT_BATTERY_IMBALANCE: ("battery_pack", "FM-BATT-001"),
            FAULT_INVERTER_COOLING: ("inverter", "FM-INV-001"),
            FAULT_MOTOR_THERMAL: ("traction_motor", "FM-MOTOR-001"),
            FAULT_COOLANT_SENSOR: ("coolant_temp_sensor", "FM-SENSOR-001"),
        }
        for index, (family, (component, code)) in enumerate(expected.items()):
            step = sample_step(
                vehicle_for_fault(family),
                18000,
                500,
                120,
                random.Random(50 + index),
            )
            self.assertIsNotNone(step.failure_event, family)
            self.assertEqual(step.failure_event["component"], component)
            self.assertEqual(step.failure_event["faultCode"], code)
            self.assertNotIn("faultFamily", step.telemetry)

    def test_environmental_confounders_do_not_create_failure_truth(self):
        for profile in ("hot_climate", "high_load"):
            vehicle = vehicle_for_fault(FAULT_HEALTHY, profile=profile)
            for tick in range(18000, 18400, 40):
                step = sample_step(vehicle, tick, 500, 120, random.Random(tick))
                self.assertIsNone(step.failure_event)


if __name__ == "__main__":
    unittest.main()
