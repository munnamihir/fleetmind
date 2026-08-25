from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DiagnosticEpisodeIntelligenceContractTests(unittest.TestCase):
    def test_episode_model_is_separate_and_run_scoped(self):
        source = (ROOT / "services/common/fleetmind_common/diagnostic_store.py").read_text()
        self.assertIn("class DiagnosticEpisode(Base):", source)
        self.assertIn('__tablename__ = "diagnostic_episodes"', source)
        self.assertIn("uq_diagnostic_episode_run_vehicle_class_start", source)
        self.assertIn("ix_diagnostic_episode_run_state_start", source)

    def test_episode_rules_are_versioned_and_event_rules_pinned(self):
        source = (ROOT / "services/common/fleetmind_common/diagnostic_episode_rules.py").read_text()
        self.assertIn('EPISODE_RULES_VERSION = "fm-diagnostic-episodes-6.9.1-v1"', source)
        self.assertIn("EPISODE_SOURCE_EVENT_RULES_VERSION = EVENT_RULES_VERSION", source)
        for state in ("EMERGING", "EVOLVING", "STABILIZED", "DESTABILIZED", "RESOLVED", "SUPERSEDED"):
            self.assertIn(state, source)

    def test_materializer_is_explicit_run_pinned_and_idempotent(self):
        source = (ROOT / "services/ml/app/diagnostic_episode_backfill.py").read_text()
        self.assertIn('"--run-id"', source)
        self.assertIn("required=True", source)
        self.assertIn("db.get(DiagnosticModelRun, run_id)", source)
        self.assertIn('"status": "already_populated"', source)
        self.assertIn('"--replace-existing"', source)
        self.assertIn("delete(DiagnosticEpisode)", source)

    def test_materializer_consumes_events_only_and_is_truth_blind(self):
        source = (ROOT / "services/ml/app/diagnostic_episode_backfill.py").read_text()
        self.assertIn("DiagnosticEvent", source)
        self.assertNotIn("DiagnosticReplayPoint", source)
        self.assertNotIn(
            "from fleetmind_common.models import Telemetry",
            source,
        )
        self.assertNotIn("select(Telemetry", source)
        self.assertNotIn("FailureEvent", source)
        self.assertNotIn("failure_events", source)
        self.assertIn('"usesPrivateFailureTruth": False', source)
        self.assertIn('"usesDiagnosticReplay": False', source)
        self.assertIn('"usesTelemetry": False', source)
        self.assertIn('"benchmarkModified": False', source)
        self.assertIn('"modelRetrained": False', source)

    def test_materializer_rejects_wrong_event_rules_version(self):
        source = (ROOT / "services/ml/app/diagnostic_episode_backfill.py").read_text()
        self.assertIn('"status": "event_rules_mismatch"', source)
        self.assertIn("EPISODE_SOURCE_EVENT_RULES_VERSION", source)
        self.assertIn("source_versions", source)

    def test_episode_boundaries_are_explicit(self):
        source = (ROOT / "services/ml/app/diagnostic_episode_backfill.py").read_text()
        self.assertIn("state=EPISODE_RESOLVED", source)
        self.assertIn(
            'close_reason="durable_return_to_healthy"',
            source,
        )
        self.assertIn("pending_resolution", source)
        self.assertIn("state=EPISODE_SUPERSEDED", source)
        self.assertIn('close_reason="hypothesis_replaced"', source)
        self.assertIn("EPISODE_START_OBSERVED_IN_PROGRESS", source)
        self.assertIn("left_censored=True", source)

    def test_api_exposes_current_run_episode_feed_and_summary(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn('@router.get("/episodes")', source)
        self.assertIn('@router.get("/episodes/summary")', source)
        self.assertIn("DiagnosticEpisode.run_id == run.id", source)
        self.assertIn("DiagnosticEpisode.experiment_id == experiment_id", source)
        self.assertIn("hypothesis_class", source)
        self.assertIn("open_only", source)

    def test_api_episode_section_is_truth_blind(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = source.split('@router.get("/episodes/summary")', 1)[1].split('@router.get("/summary")', 1)[0]
        self.assertNotIn("FailureEvent", section)
        self.assertNotIn("failure_events", section)
        self.assertIn('"usesPrivateFailureTruth": False', section)
        self.assertIn('"eventDerivedOnly": True', section)

    def test_ui_uses_episode_api_and_safe_semantics(self):
        source = (ROOT / "web/src/DiagnosticEpisodeIntelligence.tsx").read_text()
        self.assertIn("/api/v1/diagnostics/episodes/summary", source)
        self.assertIn("/api/v1/diagnostics/episodes?", source)
        self.assertIn("DIAGNOSTIC EPISODE INTELLIGENCE", source)
        self.assertIn("not physical degradation", source)
        self.assertIn("not calibrated risk", source)
        self.assertIn("onSelectVehicle(episode.vehicleId)", source)

    def test_dashboard_mounts_episode_above_raw_event_feed(self):
        source = (ROOT / "web/src/RootCauseDashboard.tsx").read_text()
        self.assertIn(
            "import { DiagnosticEpisodeIntelligence } from './DiagnosticEpisodeIntelligence';",
            source,
        )
        self.assertIn("<DiagnosticEpisodeIntelligence", source)
        self.assertIn("<DiagnosticEventFeed", source)
        self.assertLess(
            source.index("<DiagnosticEpisodeIntelligence"),
            source.index("<DiagnosticEventFeed"),
        )


if __name__ == "__main__":
    unittest.main()
