from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class PrognosticMaintenanceContractTests(unittest.TestCase):
    def test_rules_are_versioned_and_threshold_explicit(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_prognostic_rules.py"
        ).read_text()
        self.assertIn(
            'PROGNOSTIC_RULES_VERSION = "fm-diagnostic-prognostics-6.12-v1"',
            source,
        )
        self.assertIn("TARGET_HYPOTHESIS_CONFIDENCE = 0.95", source)
        self.assertIn("MIN_TRAJECTORY_POINTS", source)

    def test_rules_explicitly_reject_physical_rul_claim(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_prognostic_rules.py"
        ).read_text()
        self.assertIn("not physical remaining useful life", " ".join(source.split()))
        self.assertIn("not a physical failure event", source)

    def test_maintenance_models_are_separate_from_evidence(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_store.py"
        ).read_text()
        self.assertIn("class DiagnosticMaintenancePlan(Base):", source)
        self.assertIn("class DiagnosticMaintenanceActivity(Base):", source)
        self.assertIn("uq_diagnostic_maintenance_plan_run_case", source)

    def test_prognostic_api_has_summary_queue_detail_backtest(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn('@router.get("/prognostics/summary")', source)
        self.assertIn('@router.get("/prognostics/queue")', source)
        self.assertIn('@router.get("/prognostics/cases/{case_id}")', source)
        self.assertIn('@router.get("/prognostics/backtest")', source)

    def test_maintenance_workflow_api_is_audited(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn('@router.get("/maintenance/plans")', source)
        self.assertIn('@router.put("/maintenance/plans/{case_id}")', source)
        self.assertIn("DiagnosticMaintenanceActivity(", source)
        self.assertIn("MAINTENANCE_ACTIVITY_STATE_CHANGED", source)

    def test_prognostics_use_replay_not_private_failure_truth(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = source.split(
            "class DiagnosticMaintenancePlanUpdate",
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]
        self.assertIn("DiagnosticReplayPoint", section)
        self.assertNotIn("FailureEvent", section)
        self.assertNotIn("Telemetry.", section)

    def test_operational_trajectory_is_case_window_scoped(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = source.split(
            "def _trajectory_payload(",
            1,
        )[1].split(
            "def _current_prognostic_records(",
            1,
        )[0]
        self.assertIn(
            "point.anchor_mileage) < float(case.start_mileage)",
            section,
        )
        self.assertIn(
            "point.anchor_mileage) > float(case.latest_mileage)",
            section,
        )

    def test_summary_declares_no_post_run_telemetry(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn('"usesPostRunTelemetry": False', source)
        self.assertIn('"usesPrivateFailureTruth": False', source)

    def test_backtest_is_model_threshold_crossing_not_failure(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn('"evaluatesModelThresholdCrossing": True', source)
        self.assertIn('"evaluatesPhysicalFailure": False', source)

    def test_ui_exposes_queue_trajectory_backtest_and_planning(self):
        source = (
            ROOT / "web/src/PrognosticMaintenanceIntelligence.tsx"
        ).read_text()
        for phrase in (
            "MAINTENANCE PRIORITY QUEUE",
            "HYPOTHESIS TRAJECTORY",
            "THRESHOLD-HORIZON BACKTEST",
            "SERVICE PLANNING",
        ):
            self.assertIn(phrase, source)

    def test_ui_labels_horizon_as_not_physical_rul(self):
        source = (
            ROOT / "web/src/PrognosticMaintenanceIntelligence.tsx"
        ).read_text()
        self.assertIn("NOT PHYSICAL RUL", source)
        self.assertIn("not physical remaining useful life", " ".join(source.split()))

    def test_root_cause_mount_order(self):
        source = (ROOT / "web/src/RootCauseDashboard.tsx").read_text()
        pattern_at = source.index("<FleetPatternIntelligence")
        prognostic_at = source.index("<PrognosticMaintenanceIntelligence")
        transition_at = source.index("<DiagnosticTransitionIntelligence")
        self.assertLess(pattern_at, prognostic_at)
        self.assertLess(prognostic_at, transition_at)

    def test_phase_does_not_train_or_modify_benchmark(self):
        api = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = api.split(
            "class DiagnosticMaintenancePlanUpdate",
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]
        rules = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_prognostic_rules.py"
        ).read_text()
        combined = api + rules
        self.assertNotIn("xgboost.train", combined)
        self.assertNotIn("DiagnosticBenchmarkSnapshot", section)


if __name__ == "__main__":
    unittest.main()
