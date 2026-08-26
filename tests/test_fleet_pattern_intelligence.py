from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class FleetPatternIntelligenceContractTests(unittest.TestCase):
    def test_rules_are_versioned_and_similarity_is_deterministic(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_pattern_rules.py"
        ).read_text()

        self.assertIn(
            'PATTERN_RULES_VERSION = "fm-diagnostic-patterns-6.11-v1"',
            source,
        )
        self.assertIn("SIMILARITY_WEIGHTS", source)
        self.assertIn("similarity_score", source)
        self.assertIn("not learned probabilities", source)

    def test_persistent_operator_memory_tables_are_separate(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_store.py"
        ).read_text()

        self.assertIn("class DiagnosticWatchlistEntry(Base):", source)
        self.assertIn("class DiagnosticInvestigationView(Base):", source)
        self.assertIn("uq_diagnostic_watchlist_run_case", source)
        self.assertIn("uq_diagnostic_investigation_view_run_name", source)

    def test_pattern_api_has_overview_clusters_similarity(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()

        self.assertIn('@router.get("/patterns/overview")', source)
        self.assertIn('@router.get("/patterns/clusters")', source)
        self.assertIn('@router.get("/patterns/similar/{case_id}")', source)
        self.assertIn("_current_pattern_records", source)

    def test_pattern_api_uses_current_cases_and_observable_telemetry(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = source.split(
            "class DiagnosticWatchlistCreate",
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]

        self.assertIn("_require_current_run", section)
        self.assertIn("DiagnosticCase.run_id == run.id", section)
        self.assertIn("Telemetry.experiment_id == experiment_id", section)
        self.assertNotIn("FailureEvent", section)

    def test_watchlist_endpoints_are_present(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()

        self.assertIn('@router.get("/watchlist")', source)
        self.assertIn('@router.post("/watchlist/{case_id}")', source)
        self.assertIn('@router.delete("/watchlist/{case_id}")', source)

    def test_saved_investigation_views_are_present(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()

        self.assertIn('@router.get("/investigation-views")', source)
        self.assertIn('@router.post("/investigation-views")', source)
        self.assertIn(
            '@router.delete("/investigation-views/{view_id}")',
            source,
        )

    def test_ui_contains_all_major_pattern_surfaces(self):
        source = (
            ROOT / "web/src/FleetPatternIntelligence.tsx"
        ).read_text()

        for phrase in (
            "HOTSPOT EXPLORER",
            "RECURRING PATTERNS",
            "CASE SIMILARITY",
            "INVESTIGATION MEMORY",
            "WATCHED CASES",
        ):
            self.assertIn(phrase, source)

    def test_root_cause_mounts_patterns_after_case_workflow(self):
        source = (ROOT / "web/src/RootCauseDashboard.tsx").read_text()

        case_at = source.index("<DiagnosticCaseIntelligence")
        pattern_at = source.index("<FleetPatternIntelligence")
        transition_at = source.index("<DiagnosticTransitionIntelligence")
        self.assertLess(case_at, pattern_at)
        self.assertLess(pattern_at, transition_at)

    def test_language_preserves_noncausal_boundary(self):
        source = (
            ROOT / "web/src/FleetPatternIntelligence.tsx"
        ).read_text()

        self.assertIn("not failure enrichment", source)
        self.assertIn("attribution or causal proof", source)

    def test_pattern_phase_does_not_train_or_touch_benchmark(self):
        rules = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_pattern_rules.py"
        ).read_text()
        api = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = api.split(
            "class DiagnosticWatchlistCreate",
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]

        combined = rules + section
        self.assertNotIn("xgboost.train", combined)
        self.assertNotIn(".fit(", combined)
        self.assertNotIn("DiagnosticBenchmarkSnapshot", combined)


if __name__ == "__main__":
    unittest.main()
