from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DiagnosticTransitionIntelligenceTests(unittest.TestCase):
    def test_api_exposes_current_run_transition_endpoint(self):
        source = (ROOT / "services" / "api" / "app" / "diagnostics.py").read_text()
        self.assertIn('@router.get("/transitions")', source)
        self.assertIn("DiagnosticReplayPoint.run_id == run.id", source)
        self.assertIn('"currentRunOnly": True', source)
        self.assertIn('"usesPrivateFailureTruth": False', source)

    def test_transition_rules_are_predeclared_and_named(self):
        source = (ROOT / "services" / "api" / "app" / "diagnostics.py").read_text()
        self.assertIn("TRANSITION_RECENT_POINTS = 5", source)
        self.assertIn("TRANSITION_ESCALATION_PER_1K_MILES = 0.01", source)
        self.assertIn("TRANSITION_STABLE_FRACTION = 0.80", source)
        self.assertIn("TRANSITION_VOLATILE_FRACTION = 0.60", source)
        self.assertIn("TRANSITION_VOLATILE_CLASS_CHANGES = 3", source)

    def test_transition_endpoint_is_failure_truth_blind(self):
        source = (ROOT / "services" / "api" / "app" / "diagnostics.py").read_text()
        section = source.split('@router.get("/transitions")', 1)[1].split('@router.get("/summary")', 1)[0]
        self.assertNotIn("FailureEvent", section)
        self.assertNotIn("failure_events", section)
        self.assertNotIn("groundTruth", section)
        self.assertIn("DiagnosticReplayPoint", section)

    def test_ui_uses_transition_endpoint_and_safe_semantics(self):
        source = (ROOT / "web" / "src" / "DiagnosticTransitionIntelligence.tsx").read_text()
        self.assertIn("/api/v1/diagnostics/transitions", source)
        self.assertIn("DIAGNOSTIC TRANSITION INTELLIGENCE", source)
        self.assertIn("PREDECLARED TRANSITION RULES", source)
        self.assertIn("not failure ground truth", source)
        self.assertIn("not calibrated risk", source)

    def test_root_cause_dashboard_mounts_transition_intelligence(self):
        source = (ROOT / "web" / "src" / "RootCauseDashboard.tsx").read_text()
        self.assertIn("import { DiagnosticTransitionIntelligence } from './DiagnosticTransitionIntelligence';", source)
        self.assertIn("<DiagnosticTransitionIntelligence", source)
        self.assertIn("onSelectVehicle={setSelectedVehicleId}", source)

    def test_phase67_does_not_modify_model_training_contract(self):
        source = (ROOT / "web" / "src" / "DiagnosticTransitionIntelligence.tsx").read_text()
        self.assertNotIn("failure_events", source)


if __name__ == "__main__":
    unittest.main()
