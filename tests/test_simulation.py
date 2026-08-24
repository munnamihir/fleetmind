import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "services" / "common"))
sys.path.insert(0, str(ROOT / "services" / "simulator"))

from fleetmind_common.risk import score_telemetry
from app.sim import Vehicle, sample


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


if __name__ == "__main__":
    unittest.main()
