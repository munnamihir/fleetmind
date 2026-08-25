from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DiagnosticEventAntiChatterTests(unittest.TestCase):
    def test_thresholds_are_unchanged_and_anti_chatter_is_declared(self):
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
        self.assertIn("EVENT_CONFIRMATION_WINDOWS = 2", source)
        self.assertIn("EVENT_COOLDOWN_ANCHORS = 4", source)

    def test_materializer_requires_confirmed_state(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_event_backfill.py"
        ).read_text()

        self.assertIn("confirmed_candidate", source)
        self.assertIn("EVENT_CONFIRMATION_WINDOWS", source)
        self.assertIn("prior_confirmed_trend", source)
        self.assertIn("previousConfirmedState", source)
        self.assertIn("confirmedState", source)

    def test_materializer_uses_family_cooldown(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_event_backfill.py"
        ).read_text()

        self.assertIn("cooldown_ready", source)
        self.assertIn("EVENT_COOLDOWN_ANCHORS", source)
        self.assertIn("last_confidence_event_index", source)
        self.assertIn("last_stability_event_index", source)

    def test_materializer_remains_truth_blind(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_event_backfill.py"
        ).read_text()

        self.assertNotIn("FailureEvent", source)
        self.assertNotIn("failure_events", source)
        self.assertIn("DiagnosticReplayPoint", source)


if __name__ == "__main__":
    unittest.main()
