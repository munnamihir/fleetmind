from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DiagnosticExtendedReplayContractTests(unittest.TestCase):
    def test_backfill_is_explicit_run_pinned_and_replace_guarded(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_extended_replay_backfill.py"
        ).read_text()

        self.assertIn('"--run-id"', source)
        self.assertIn("required=True", source)
        self.assertIn('"--replace-existing"', source)
        self.assertIn('"status": "replace_required"', source)
        self.assertIn("db.get(DiagnosticModelRun, run_id)", source)

    def test_history_is_frozen_at_persisted_prediction_anchor(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_extended_replay_backfill.py"
        ).read_text()

        self.assertIn("FROM diagnostic_predictions", source)
        self.assertIn("WHERE run_id = :run_id", source)
        self.assertIn("t.timestamp <= c.anchor_timestamp", source)
        self.assertIn('"usesPostRunTelemetry": False', source)

    def test_extended_replay_is_truth_blind(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_extended_replay_backfill.py"
        ).read_text()

        self.assertNotIn("FailureEvent", source)
        self.assertNotIn("failure_events", source)
        self.assertIn('"usesPrivateFailureTruth": False', source)
        self.assertIn('"failureMarkersExposed": False', source)

    def test_bundle_identity_and_schema_are_verified(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_extended_replay_backfill.py"
        ).read_text()

        self.assertIn('bundle.get("experimentId")', source)
        self.assertIn('bundle.get("lineage")', source)
        self.assertIn('bundle.get("featureSchemaSha256")', source)
        self.assertIn('bundle.get("champion")', source)

    def test_default_history_is_bounded(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_extended_replay_backfill.py"
        ).read_text()

        self.assertIn("EXTENDED_ROWS_PER_VEHICLE = 600", source)
        self.assertIn("EXTENDED_MAX_POINTS_PER_VEHICLE = 64", source)
        self.assertIn("_evenly_spaced_anchor_indexes", source)

    def test_transition_api_distinguishes_historical_emergence_from_new(self):
        source = (
            ROOT / "services" / "api" / "app" / "diagnostics.py"
        ).read_text()

        self.assertIn('"emergenceObserved"', source)
        self.assertIn('"firstEmergenceMileage"', source)
        self.assertIn('"historicalTransitions"', source)
        self.assertIn('"newlyEmerging"', source)

    def test_transition_ui_surfaces_historical_context(self):
        source = (
            ROOT
            / "web"
            / "src"
            / "DiagnosticTransitionIntelligence.tsx"
        ).read_text()

        self.assertIn("Emergence observed", source)
        self.assertIn("Historical transitions", source)
        self.assertIn("firstEmergenceMileage", source)

    def test_replay_ui_no_longer_claims_short_loader_metadata(self):
        source = (
            ROOT / "web" / "src" / "DiagnosticReplay.tsx"
        ).read_text()

        self.assertIn("persisted observable anchors", source)
        self.assertNotIn("observable rows · stride", source)


if __name__ == "__main__":
    unittest.main()
