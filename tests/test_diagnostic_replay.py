from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DiagnosticReplayContractTests(unittest.TestCase):
    def test_store_has_separate_replay_table(self):
        source = (
            ROOT
            / "services"
            / "common"
            / "fleetmind_common"
            / "diagnostic_store.py"
        ).read_text()

        self.assertIn("class DiagnosticReplayPoint", source)
        self.assertIn('__tablename__ = "diagnostic_replay_points"', source)
        self.assertIn(
            'name="uq_diagnostic_replay_run_vehicle_anchor"',
            source,
        )

    def test_trainer_scores_replay_from_observable_history(self):
        source = (
            ROOT / "services" / "ml" / "app" / "diagnostic_run.py"
        ).read_text()

        self.assertIn("REPLAY_ROWS_PER_VEHICLE", source)
        self.assertIn("REPLAY_STRIDE", source)
        self.assertIn("def replay_scoring_examples(", source)
        self.assertIn("DiagnosticReplayPoint(", source)
        self.assertIn('"replayPolicy": "observable_only_same_run"', source)

        section = source.split(
            "def load_current_scoring_telemetry(",
            1,
        )[1].split(
            "def _aligned_probabilities(",
            1,
        )[0]
        self.assertNotIn("failure_events", section)
        self.assertNotIn("failure_cutoffs", section)

    def test_backfill_reuses_existing_trained_run_bundle(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_replay_backfill.py"
        ).read_text()

        # Phase 6.6.1 deliberately pins replay to an explicit persisted
        # diagnostic run instead of following whichever experiment is active.
        self.assertIn('"--run-id"', source)
        self.assertIn("required=True", source)
        self.assertIn("db.get(DiagnosticModelRun, run_id)", source)

        # The persisted run owns the experiment/lineage/champion identity and
        # its already-trained artifact is reused rather than retraining.
        self.assertIn("experiment_id = run.experiment_id", source)
        self.assertIn("joblib.load(path)", source)
        self.assertIn("bundle_champion", source)
        self.assertIn("load_current_scoring_telemetry(", source)

        # Do not silently redirect replay to a newer simulator experiment.
        self.assertNotIn("latest_trained_run", source)
        self.assertNotIn("active_experiment_id(", source)


    def test_api_timeline_is_current_run_scoped_and_truth_blind(self):
        source = (
            ROOT / "services" / "api" / "app" / "diagnostics.py"
        ).read_text()

        self.assertIn(
            '@router.get("/vehicles/{vehicle_id}/timeline")',
            source,
        )
        self.assertIn("DiagnosticReplayPoint.run_id == run.id", source)
        self.assertIn('"usesPrivateFailureTruth": False', source)
        self.assertIn('"failureMarkersExposed": False', source)

        timeline_section = source.split(
            '@router.get("/vehicles/{vehicle_id}/timeline")',
            1,
        )[1].split('@router.get("/summary")', 1)[0]

        self.assertNotIn("FailureEvent", timeline_section)
        self.assertNotIn("failure_events", timeline_section)

    def test_ui_fetches_timeline_and_exposes_replay_controls(self):
        source = (
            ROOT / "web" / "src" / "DiagnosticReplay.tsx"
        ).read_text()

        self.assertIn("/timeline?limit=64", source)
        self.assertIn("INCIDENT REPLAY", source)
        self.assertIn('type="range"', source)
        self.assertIn("COMPETING HYPOTHESES", source)
        self.assertIn("OBSERVED SIGNALS", source)
        self.assertIn("hidden failure markers are intentionally", source)

    def test_root_cause_dashboard_mounts_replay(self):
        source = (
            ROOT / "web" / "src" / "RootCauseDashboard.tsx"
        ).read_text()

        self.assertIn(
            "import { DiagnosticReplay } from './DiagnosticReplay';",
            source,
        )
        self.assertIn("<DiagnosticReplay", source)
        self.assertIn("vehicleId={selectedVehicleId}", source)


if __name__ == "__main__":
    unittest.main()
