from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DiagnosticEventIntelligenceContractTests(unittest.TestCase):
    def test_event_model_is_separate_and_run_scoped(self):
        source = (
            ROOT
            / "services"
            / "common"
            / "fleetmind_common"
            / "diagnostic_store.py"
        ).read_text()

        self.assertIn("class DiagnosticEvent(Base):", source)
        self.assertIn('__tablename__ = "diagnostic_events"', source)
        self.assertIn("uq_diagnostic_event_run_vehicle_type_anchor", source)
        self.assertIn("ix_diagnostic_event_run_type_timestamp", source)

    def test_event_types_and_rules_are_fixed(self):
        source = (
            ROOT
            / "services"
            / "common"
            / "fleetmind_common"
            / "diagnostic_event_rules.py"
        ).read_text()

        self.assertIn('EVENT_RULES_VERSION = "fm-diagnostic-events-6.8.1-v1"', source)
        self.assertIn("EVENT_RECENT_POINTS = 5", source)
        self.assertIn("EVENT_INCIDENT_CONFIDENCE = 0.70", source)
        self.assertIn("EVENT_ESCALATION_PER_1K_MILES = 0.01", source)
        self.assertIn("EVENT_STABLE_FRACTION = 0.80", source)
        self.assertIn("EVENT_VOLATILE_FRACTION = 0.60", source)

        for event_type in (
            "HYPOTHESIS_EMERGED",
            "HYPOTHESIS_CHANGED",
            "CONFIDENCE_ESCALATED",
            "CONFIDENCE_DEESCALATED",
            "HYPOTHESIS_STABILIZED",
            "HYPOTHESIS_DESTABILIZED",
        ):
            self.assertIn(event_type, source)

    def test_backfill_is_explicit_run_pinned_and_truth_blind(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_event_backfill.py"
        ).read_text()

        self.assertIn('"--run-id"', source)
        self.assertIn("required=True", source)
        self.assertIn("db.get(DiagnosticModelRun, run_id)", source)
        self.assertIn("DiagnosticReplayPoint", source)
        self.assertNotIn("FailureEvent", source)
        self.assertNotIn("failure_events", source)
        self.assertIn('"usesPrivateFailureTruth": False', source)
        self.assertIn('"benchmarkModified": False', source)
        self.assertIn('"modelRetrained": False', source)

    def test_event_materialization_is_idempotent_and_replaceable(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_event_backfill.py"
        ).read_text()

        self.assertIn('"status": "already_populated"', source)
        self.assertIn('"--replace-existing"', source)
        self.assertIn("delete(DiagnosticEvent)", source)

    def test_api_exposes_current_run_event_feed_and_summary(self):
        source = (
            ROOT / "services" / "api" / "app" / "diagnostics.py"
        ).read_text()

        self.assertIn('@router.get("/events")', source)
        self.assertIn('@router.get("/events/summary")', source)
        self.assertIn("DiagnosticEvent.run_id == run.id", source)
        self.assertIn("DiagnosticEvent.experiment_id == experiment_id", source)
        self.assertIn("event_type", source)
        self.assertIn("hypothesis_class", source)
        self.assertIn("min_confidence", source)

    def test_api_event_section_never_queries_private_truth(self):
        source = (
            ROOT / "services" / "api" / "app" / "diagnostics.py"
        ).read_text()

        section = source.split(
            '@router.get("/events")',
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]

        self.assertNotIn("FailureEvent", section)
        self.assertNotIn("failure_events", section)
        self.assertIn('"usesPrivateFailureTruth": False', section)

    def test_ui_fetches_event_feed_and_uses_noncausal_language(self):
        source = (
            ROOT / "web" / "src" / "DiagnosticEventFeed.tsx"
        ).read_text()

        self.assertIn("/api/v1/diagnostics/events/summary", source)
        self.assertIn("/api/v1/diagnostics/events?", source)
        self.assertIn("DIAGNOSTIC EVENT INTELLIGENCE", source)
        self.assertIn("not physical failure events", source)
        self.assertIn("not calibrated", source)
        self.assertIn("onSelectVehicle(event.vehicleId)", source)

    def test_root_cause_dashboard_mounts_event_feed(self):
        source = (
            ROOT / "web" / "src" / "RootCauseDashboard.tsx"
        ).read_text()

        self.assertIn(
            "import { DiagnosticEventFeed } from './DiagnosticEventFeed';",
            source,
        )
        self.assertIn("<DiagnosticEventFeed", source)
        self.assertIn("onSelectVehicle={setSelectedVehicleId}", source)


if __name__ == "__main__":
    unittest.main()
