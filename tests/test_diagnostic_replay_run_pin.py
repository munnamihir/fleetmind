from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DiagnosticReplayRunPinContractTests(unittest.TestCase):
    def test_backfill_requires_explicit_run_id(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_replay_backfill.py"
        ).read_text()

        self.assertIn('"--run-id"', source)
        self.assertIn("required=True", source)
        self.assertIn("db.get(DiagnosticModelRun, run_id)", source)

    def test_run_experiment_is_authoritative(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_replay_backfill.py"
        ).read_text()

        self.assertIn("experiment_id = run.experiment_id", source)
        self.assertIn(
            "load_current_scoring_telemetry(\n            db,\n            experiment_id,",
            source,
        )
        self.assertNotIn("active_experiment_id(", source)

    def test_bundle_identity_is_verified(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_replay_backfill.py"
        ).read_text()

        self.assertIn(
            "Model bundle experiment does not match persisted diagnostic run",
            source,
        )
        self.assertIn(
            "Model bundle lineage does not match persisted diagnostic run",
            source,
        )
        self.assertIn(
            "Model bundle champion does not match persisted diagnostic run",
            source,
        )

    def test_backfill_is_truth_blind_and_idempotent(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_replay_backfill.py"
        ).read_text()

        self.assertIn('"usesPrivateFailureTruth": False', source)
        self.assertIn('"failureMarkersExposed": False', source)
        self.assertIn('"runPinned": True', source)
        self.assertIn('"already_populated"', source)
        self.assertNotIn("FailureEvent", source)
        self.assertNotIn("failure_events", source)


if __name__ == "__main__":
    unittest.main()
