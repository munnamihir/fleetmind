from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class OperationalAutomationContractTests(unittest.TestCase):
    def test_rules_are_versioned_and_default_policies_require_approval(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_automation_rules.py"
        ).read_text()
        self.assertIn(
            'AUTOMATION_RULES_VERSION = "fm-diagnostic-automation-6.13-v1"',
            source,
        )
        self.assertIn('"requiresApproval": True', source)
        self.assertNotIn('"requiresApproval": False', source)

    def test_rules_only_allow_non_destructive_workflow_actions(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_automation_rules.py"
        ).read_text()
        self.assertIn('"ENSURE_REVIEW_PLAN"', source)
        self.assertIn('"ENSURE_WATCHLIST"', source)
        self.assertNotIn('"CLOSE_CASE"', source)
        self.assertNotIn('"SET_FAILURE"', source)

    def test_automation_models_are_separate_persistent_workflow_metadata(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_store.py"
        ).read_text()
        self.assertIn("class DiagnosticAutomationPolicy(Base):", source)
        self.assertIn("class DiagnosticAutomationAction(Base):", source)
        self.assertIn("class DiagnosticAutomationActivity(Base):", source)
        self.assertIn("uq_diagnostic_automation_policy_run_key", source)
        self.assertIn("uq_diagnostic_automation_action_run_case_policy", source)

    def test_api_has_bootstrap_simulate_evaluate_and_summary(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn('@router.post("/automation/policies/bootstrap")', source)
        self.assertIn('@router.get("/automation/simulate")', source)
        self.assertIn('@router.post("/automation/evaluate")', source)
        self.assertIn('@router.get("/automation/summary")', source)

    def test_api_has_action_lifecycle_endpoints(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        for endpoint in (
            '@router.get("/automation/actions")',
            '@router.get("/automation/actions/{action_id}")',
            '@router.post("/automation/actions/{action_id}/approve")',
            '@router.post("/automation/actions/{action_id}/reject")',
            '@router.post("/automation/actions/{action_id}/execute")',
        ):
            self.assertIn(endpoint, source)

    def test_evaluation_never_executes_actions(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = source.split(
            "def evaluate_diagnostic_automation(",
            1,
        )[1].split(
            '@router.get("/automation/summary")',
            1,
        )[0]
        self.assertIn("AUTOMATION_STATUS_PENDING_APPROVAL", section)
        self.assertIn('"executionPerformed": False', section)
        self.assertNotIn("_execute_approved_automation_workflow(", section)

    def test_execute_requires_approved_status(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = source.split(
            "def execute_diagnostic_automation_action(",
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]
        self.assertIn(
            "row.status != AUTOMATION_STATUS_APPROVED",
            section,
        )
        self.assertIn("Human approval is required", section)

    def test_execution_does_not_overwrite_existing_maintenance_plan(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = source.split(
            "def _execute_approved_automation_workflow(",
            1,
        )[1].split(
            "def execute_diagnostic_automation_action(",
            1,
        )[0]
        self.assertIn('"outcome": "ALREADY_EXISTS"', section)
        self.assertIn("DiagnosticMaintenancePlan(", section)
        self.assertNotIn("plan.state =", section)
        self.assertNotIn("case.status =", section)
        self.assertNotIn("case.review_priority =", section)

    def test_automation_section_is_truth_blind_and_benchmark_safe(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = source.split(
            "class DiagnosticAutomationActorRequest",
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]
        self.assertNotIn("FailureEvent", section)
        self.assertNotIn("DiagnosticBenchmarkSnapshot", section)
        self.assertNotIn("xgboost.train", section)
        self.assertIn('"usesPrivateFailureTruth": False', section)
        self.assertIn('"benchmarkModified": False', section)

    def test_policy_conditions_cannot_be_edited_by_api(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        update_model = source.split(
            "class DiagnosticAutomationPolicyUpdate",
            1,
        )[1].split(
            "def _automation_policy_payload",
            1,
        )[0]
        self.assertIn("enabled: bool", update_model)
        self.assertNotIn("conditions", update_model)
        self.assertNotIn("priority:", update_model)

    def test_ui_has_policy_simulation_queue_and_guarded_execution(self):
        source = (
            ROOT / "web/src/OperationalAutomationIntelligence.tsx"
        ).read_text()
        for phrase in (
            "PINNED POLICIES",
            "DRY-RUN SIMULATOR",
            "APPROVAL QUEUE",
            "GUARDED EXECUTION",
            "ACTION AUDIT TRAIL",
        ):
            self.assertIn(phrase, source)

    def test_ui_explicitly_requires_human_approval(self):
        source = (
            ROOT / "web/src/OperationalAutomationIntelligence.tsx"
        ).read_text()
        normalized = " ".join(source.split())
        self.assertIn("HUMAN APPROVAL REQUIRED", source)
        self.assertIn("Nothing executes without an explicit human approval", normalized)
        self.assertIn("No private failure truth", normalized)

    def test_ui_execution_button_only_enabled_for_approved_action(self):
        source = (
            ROOT / "web/src/OperationalAutomationIntelligence.tsx"
        ).read_text()
        self.assertIn("selected.status !== 'APPROVED'", source)
        self.assertIn("Execute approved action", source)

    def test_root_cause_mount_order(self):
        source = (ROOT / "web/src/RootCauseDashboard.tsx").read_text()
        prognostic_at = source.index("<PrognosticMaintenanceIntelligence")
        automation_at = source.index("<OperationalAutomationIntelligence")
        transition_at = source.index("<DiagnosticTransitionIntelligence")
        self.assertLess(prognostic_at, automation_at)
        self.assertLess(automation_at, transition_at)

    def test_phase_does_not_retrain_or_modify_frozen_benchmark(self):
        api = (ROOT / "services/api/app/diagnostics.py").read_text()
        rules = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_automation_rules.py"
        ).read_text()
        combined = api + rules
        self.assertNotIn("xgboost.train", combined)
        self.assertIn('"modelRetrained": False', api)
        self.assertIn('"benchmarkModified": False', api)


if __name__ == "__main__":
    unittest.main()
