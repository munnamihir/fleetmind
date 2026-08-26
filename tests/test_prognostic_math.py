from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
RULES = (
    ROOT
    / "services/common/fleetmind_common/diagnostic_prognostic_rules.py"
)

spec = importlib.util.spec_from_file_location(
    "diagnostic_prognostic_rules",
    RULES,
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class PrognosticMathTests(unittest.TestCase):
    def test_linear_fit_recovers_positive_slope(self):
        points = [
            (10000.0 + i * 1000.0, 0.50 + i * 0.02)
            for i in range(10)
        ]
        fit = module.fit_trajectory(points)
        self.assertIsNotNone(fit)
        assert fit is not None
        self.assertAlmostEqual(fit["slopePer1kMiles"], 0.02, places=6)
        self.assertAlmostEqual(fit["rSquared"], 1.0, places=6)

    def test_horizon_estimate_is_distance_to_model_threshold(self):
        horizon = module.estimate_threshold_horizon(
            latest_confidence=0.85,
            slope_per_1k_miles=0.02,
            slope_std_error_per_1k_miles=0.0,
        )
        self.assertAlmostEqual(
            horizon["estimatedMilesToThreshold"],
            5000.0,
            places=4,
        )

    def test_flat_trajectory_has_no_horizon(self):
        horizon = module.estimate_threshold_horizon(
            latest_confidence=0.70,
            slope_per_1k_miles=0.0,
            slope_std_error_per_1k_miles=0.0,
        )
        self.assertIsNone(horizon["estimatedMilesToThreshold"])

    def test_threshold_already_reached_is_zero_horizon(self):
        horizon = module.estimate_threshold_horizon(
            latest_confidence=0.97,
            slope_per_1k_miles=0.02,
            slope_std_error_per_1k_miles=0.001,
        )
        self.assertEqual(horizon["estimatedMilesToThreshold"], 0.0)
        self.assertTrue(horizon["thresholdAlreadyReached"])

    def test_priority_score_is_deterministic(self):
        result = module.maintenance_priority(
            review_priority="HIGH",
            episode_state="DESTABILIZED",
            latest_confidence=0.98,
            slope_per_1k_miles=0.04,
            estimated_miles_to_threshold=1000.0,
            watchlisted=True,
        )
        self.assertEqual(result["maintenanceTier"], "URGENT_REVIEW")
        self.assertEqual(
            result["recommendedReviewWindow"],
            "WITHIN_2500_MI",
        )

    def test_backtest_targets_future_model_threshold(self):
        points = [
            (10000.0 + i * 1000.0, min(0.99, 0.55 + i * 0.03))
            for i in range(20)
        ]
        result = module.backtest_threshold_horizon(points)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("predictedMilesToThreshold", result)
        self.assertIn("observedFutureCrossingMiles", result)


if __name__ == "__main__":
    unittest.main()
