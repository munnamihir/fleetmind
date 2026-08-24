import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "common"))

from fleetmind_common.risk import score_telemetry


def event(pump_current=3.1, pump_rpm=2700, coolant=43, battery=35, imbalance=.012, inverter=69):
    return {
        "battery": {"temperatureC": battery, "cellImbalanceV": imbalance},
        "powertrain": {"inverterTempC": inverter},
        "thermal": {"pumpCurrentA": pump_current, "pumpRPM": pump_rpm, "coolantTempC": coolant},
    }


class RiskModelTests(unittest.TestCase):
    def test_healthy_vehicle_scores_low(self):
        result = score_telemetry(event())
        self.assertEqual(result.status, "healthy")
        self.assertLess(result.score, 0.10)

    def test_degraded_pump_is_detected(self):
        result = score_telemetry(event(pump_current=4.45, pump_rpm=2070, coolant=53, battery=43))
        self.assertIn(result.status, {"degraded", "critical"})
        self.assertGreater(result.score, 0.55)
        self.assertTrue(any("pump current" in x for x in result.evidence))
        self.assertTrue(any("pump RPM" in x for x in result.evidence))

    def test_multiple_signals_raise_risk_more_than_single_signal(self):
        single = score_telemetry(event(pump_current=4.2))
        combined = score_telemetry(event(pump_current=4.2, pump_rpm=2150, coolant=54, battery=44))
        self.assertGreater(combined.score, single.score)


if __name__ == "__main__":
    unittest.main()
