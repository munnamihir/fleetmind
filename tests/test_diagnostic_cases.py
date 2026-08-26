from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DiagnosticCaseIntelligenceContractTests(unittest.TestCase):
    def test_case_rules_are_versioned_and_episode_pinned(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_case_rules.py"
        ).read_text()

        self.assertIn(
            'CASE_RULES_VERSION = "fm-diagnostic-cases-6.10-v1"',
            source,
        )
        self.assertIn(
            "CASE_SOURCE_EPISODE_RULES_VERSION = EPISODE_RULES_VERSION",
            source,
        )
        self.assertIn("derive_case_review_priority", source)

    def test_case_and_activity_models_are_separate_and_run_scoped(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_store.py"
        ).read_text()

        self.assertIn("class DiagnosticCase(Base):", source)
        self.assertIn('ForeignKey("diagnostic_model_runs.id"', source)
        self.assertIn('ForeignKey("diagnostic_episodes.id"', source)
        self.assertIn("class DiagnosticCaseActivity(Base):", source)
        self.assertIn(
            "uq_diagnostic_case_run_episode",
            source,
        )

    def test_materializer_consumes_episodes_only(self):
        source = (
            ROOT
            / "services/ml/app/diagnostic_case_materialize.py"
        ).read_text()

        self.assertIn("DiagnosticEpisode", source)
        self.assertNotIn("DiagnosticEvent,", source)
        self.assertNotIn("DiagnosticReplayPoint", source)
        self.assertNotIn("DiagnosticPrediction", source)
        self.assertNotIn("FailureEvent", source)
        self.assertNotIn("from fleetmind_common.models import", source)

    def test_materializer_is_explicit_run_pinned_and_non_destructive(self):
        source = (
            ROOT
            / "services/ml/app/diagnostic_case_materialize.py"
        ).read_text()

        self.assertIn('"--run-id"', source)
        self.assertIn("required=True", source)
        self.assertNotIn("--replace-existing", source)
        self.assertIn('"existingWorkflowPreserved": True', source)

    def test_case_api_has_feed_summary_detail_and_workflow(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()

        self.assertIn('@router.get("/cases")', source)
        self.assertIn('@router.get("/cases/summary")', source)
        self.assertIn('@router.get("/cases/{case_id}")', source)
        self.assertIn('@router.patch("/cases/{case_id}")', source)
        self.assertIn(
            '@router.post("/cases/{case_id}/notes")',
            source,
        )

    def test_case_api_remains_current_run_scoped(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()

        case_section = source.split(
            'def _diagnostic_case_payload',
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]
        self.assertIn("_require_current_run", case_section)
        self.assertIn("DiagnosticCase.run_id == run.id", case_section)
        self.assertIn(
            "DiagnosticCase.experiment_id == experiment_id",
            case_section,
        )

    def test_ui_exposes_real_workflow_controls(self):
        source = (
            ROOT / "web/src/DiagnosticCaseIntelligence.tsx"
        ).read_text()

        self.assertIn("/api/v1/diagnostics/cases/summary", source)
        self.assertIn("method: 'PATCH'", source)
        self.assertIn("/notes", source)
        self.assertIn("Assigned to", source)
        self.assertIn("Investigation note", source)
        self.assertIn("AUDIT TRAIL", source)

    def test_root_cause_mounts_case_intelligence_before_transitions(self):
        source = (ROOT / "web/src/RootCauseDashboard.tsx").read_text()

        case_at = source.index("<DiagnosticCaseIntelligence")
        transition_at = source.index("<DiagnosticTransitionIntelligence")
        self.assertLess(case_at, transition_at)

    def test_case_language_is_noncausal(self):
        source = (
            ROOT / "web/src/DiagnosticCaseIntelligence.tsx"
        ).read_text()

        self.assertIn("not physical-failure truth", source)
        self.assertIn("not physical-failure truth, attribution or causal proof", source)

    def test_case_phase_does_not_touch_training_or_benchmark(self):
        rules = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_case_rules.py"
        ).read_text()
        materializer = (
            ROOT
            / "services/ml/app/diagnostic_case_materialize.py"
        ).read_text()

        combined = rules + materializer
        self.assertNotIn("xgboost.train", combined)
        self.assertNotIn("fit(", combined)
        self.assertIn('"benchmarkModified": False', materializer)
        self.assertIn('"modelRetrained": False', materializer)


if __name__ == "__main__":
    unittest.main()
