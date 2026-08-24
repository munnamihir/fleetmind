import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "common"))

from fleetmind_common.firmware import (
    FirmwareObservation,
    classify_regression,
    compare_firmware,
    hardware_interactions,
)


def obs(
    firmware: str,
    failed: bool,
    *,
    pump: str = "CP-17",
    factory: str = "Austin",
    model: str = "SY",
    mileage: float = 50000,
    ambient: float = 34,
    risk: float = 0.2,
) -> FirmwareObservation:
    return FirmwareObservation(
        firmware=firmware,
        pump_revision=pump,
        factory=factory,
        model=model,
        mileage=mileage,
        ambient_temp_c=ambient,
        failed=failed,
        risk_score=risk,
        non_healthy=risk >= 0.25,
        pump_current_a=3.1 + risk,
    )


class FirmwareRegressionTests(unittest.TestCase):
    def test_matching_excludes_unshared_strata(self):
        observations = [
            obs("2026.32.4", True),
            obs("2026.32.1", False),
            obs("2026.32.4", True, mileage=90000),
        ]
        result = compare_firmware(observations, "2026.32.4", "2026.32.1")
        self.assertEqual(result["matching"]["matchedPopulation"], 2)
        self.assertEqual(result["matching"]["matchedStrata"], 1)

    def test_regression_signal_has_elevated_effect(self):
        observations = []
        for index in range(40):
            observations.append(obs("2026.32.4", index < 12, risk=0.45))
        for index in range(40):
            observations.append(obs("2026.32.1", index < 2, risk=0.08))

        result = compare_firmware(observations, "2026.32.4", "2026.32.1")
        self.assertGreater(result["outcomes"]["riskRatio"], 2.0)
        self.assertLess(result["outcomes"]["pValue"], 0.05)
        self.assertIn(result["classification"], {"regression", "critical_regression"})
        self.assertGreater(result["telemetrySignals"]["averageRiskDelta"], 0)

    def test_stable_firmware_is_not_flagged(self):
        observations = []
        for index in range(50):
            observations.append(obs("A", index < 4, risk=0.1))
            observations.append(obs("B", index < 4, risk=0.1))
        result = compare_firmware(observations, "A", "B")
        self.assertEqual(result["classification"], "stable")

    def test_hardware_interaction_ranks_problem_revision_first(self):
        observations = []
        for index in range(30):
            observations.append(obs("new", index < 10, pump="CP-17", risk=0.4))
            observations.append(obs("old", index < 1, pump="CP-17", risk=0.08))
            observations.append(obs("new", False, pump="CP-16", risk=0.05))
            observations.append(obs("old", False, pump="CP-16", risk=0.05))
        rows = hardware_interactions(observations, "new", "old")
        self.assertEqual(rows[0]["pumpRevision"], "CP-17")
        self.assertGreater(rows[0]["absoluteRiskIncrease"], rows[1]["absoluteRiskIncrease"])

    def test_classifier_requires_evidence(self):
        classification = classify_regression(
            matched_population=10,
            total_failures=1,
            risk_ratio=9.0,
            p_value=0.001,
            absolute_risk_increase=0.4,
        )
        self.assertEqual(classification, "insufficient_data")


if __name__ == "__main__":
    unittest.main()
