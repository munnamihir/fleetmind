from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DiagnosticEpisodeContinuityContractTests(unittest.TestCase):
    def test_continuity_rules_are_explicit_and_versioned(self):
        source = (
            ROOT
            / "services"
            / "common"
            / "fleetmind_common"
            / "diagnostic_episode_rules.py"
        ).read_text()

        self.assertIn(
            'EPISODE_RULES_VERSION = "fm-diagnostic-episodes-6.9.1-v1"',
            source,
        )
        self.assertIn(
            "EPISODE_CONTINUITY_MAX_HEALTHY_GAP_MILES = 1000.0",
            source,
        )
        self.assertIn(
            "EPISODE_CONTINUITY_MAX_INTERVENING_HEALTHY_EVENTS = 1",
            source,
        )
        self.assertIn(
            "EPISODE_SOURCE_EVENT_RULES_VERSION = EVENT_RULES_VERSION",
            source,
        )

    def test_continuity_is_same_class_only(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_episode_backfill.py"
        ).read_text()

        self.assertIn("_can_continue_same_class", source)
        self.assertIn(
            'event.current_class != active["hypothesis_class"]',
            source,
        )
        self.assertIn(
            "EPISODE_CONTINUITY_MAX_HEALTHY_GAP_MILES",
            source,
        )
        self.assertIn(
            "EPISODE_CONTINUITY_MAX_INTERVENING_HEALTHY_EVENTS",
            source,
        )

    def test_resolution_is_deferred_not_deleted(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_episode_backfill.py"
        ).read_text()

        self.assertIn("pending_resolution", source)
        self.assertIn('"durable_return_to_healthy"', source)
        self.assertIn(
            '"end_of_event_stream_after_healthy"',
            source,
        )
        self.assertIn("_record_continuation", source)

    def test_raw_event_stream_remains_unchanged(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_episode_backfill.py"
        ).read_text()

        self.assertNotIn("delete(DiagnosticEvent)", source)
        self.assertNotIn("update(DiagnosticEvent)", source)
        self.assertIn("DiagnosticEvent", source)
        self.assertNotIn("DiagnosticReplayPoint", source)
        self.assertNotIn("FailureEvent", source)

    def test_model_and_benchmark_are_untouched(self):
        source = (
            ROOT
            / "services"
            / "ml"
            / "app"
            / "diagnostic_episode_backfill.py"
        ).read_text()

        self.assertIn('"modelRetrained": False', source)
        self.assertIn('"benchmarkModified": False', source)
        self.assertIn('"eventDerivedOnly": True', source)
        self.assertIn('"usesPrivateFailureTruth": False', source)


if __name__ == "__main__":
    unittest.main()
