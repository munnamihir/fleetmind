from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = (
    ROOT / "services" / "ml" / "app" / "diagnostic_run.py"
).read_text()


class FailureAwareSamplingContractTests(unittest.TestCase):
    def test_training_sampling_is_per_vehicle_and_bounded(self):
        self.assertIn("PARTITION BY t.vehicle_id", SOURCE)
        self.assertIn(
            "vehicle_row_number <= :per_vehicle_limit",
            SOURCE,
        )
        self.assertIn("max_total_rows // vehicle_count", SOURCE)

    def test_failed_training_rows_stop_at_failure_timestamp(self):
        self.assertIn("WITH failure_cutoffs AS", SOURCE)
        self.assertIn("t.timestamp <= f.occurred_at", SOURCE)

    def test_operational_scoring_has_its_own_latest_window_query(self):
        section = SOURCE.split(
            "def load_current_scoring_telemetry(",
            1,
        )[1].split(
            "def _aligned_probabilities(",
            1,
        )[0]

        self.assertIn(
            "vehicle_row_number <= :window_size",
            section,
        )
        self.assertNotIn("JOIN failure", section)
        self.assertNotIn("failure_cutoffs", section)
        self.assertIn(
            '"usesPrivateFailureTruth": False',
            SOURCE,
        )

    def test_scoring_helper_uses_renamed_parameter(self):
        self.assertIn(
            "for vehicle_id, raw_points in sorted(scoring_by_vehicle.items()):",
            SOURCE,
        )
        self.assertNotIn(
            "for vehicle_id, raw_points in sorted(by_vehicle.items()):",
            SOURCE,
        )

    def test_global_latest_fleet_limit_is_removed(self):
        self.assertNotIn(
            "ORDER BY id DESC\\n                LIMIT :max_rows",
            SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
