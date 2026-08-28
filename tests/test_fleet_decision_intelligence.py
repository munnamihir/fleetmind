from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class FleetDecisionIntelligenceContractTests(unittest.TestCase):
    def test_rules_are_versioned(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/fleet_decision_rules.py"
        ).read_text()
        self.assertIn(
            'FLEET_DECISION_RULES_VERSION = "fm-fleet-decision-7.0-v1"',
            source,
        )

    def test_rules_explicitly_reject_physical_risk_claims(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/fleet_decision_rules.py"
        ).read_text()
        normalized = " ".join(source.split())
        self.assertIn("not physical failure risk", normalized)
        self.assertIn("not labor hours", normalized)

    def test_snapshot_model_is_separate_derived_state(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_store.py"
        ).read_text()
        self.assertIn("class DiagnosticFleetDecisionSnapshot(Base):", source)
        self.assertIn("uq_fleet_decision_snapshot_run_hash", source)

    def test_api_has_summary_and_vehicle_endpoints(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn('@router.get("/fleet-intelligence/summary")', source)
        self.assertIn('@router.get("/fleet-intelligence/vehicles")', source)
        self.assertIn(
            '@router.get("/fleet-intelligence/vehicles/{vehicle_id}")',
            source,
        )

    def test_api_has_coverage_and_cohorts(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn('@router.get("/fleet-intelligence/coverage")', source)
        self.assertIn('@router.get("/fleet-intelligence/cohorts")', source)

    def test_api_has_no_write_scenario(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = source.split(
            '@router.post("/fleet-intelligence/scenario")',
            1,
        )[1].split(
            '@router.post("/fleet-intelligence/snapshots")',
            1,
        )[0]
        self.assertIn('"simulationOnly": True', section)
        self.assertNotIn("db.add(", section)
        self.assertNotIn("db.commit(", section)

    def test_snapshot_endpoints_are_versioned_and_idempotent(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn('@router.post("/fleet-intelligence/snapshots")', source)
        self.assertIn('@router.get("/fleet-intelligence/snapshots")', source)
        self.assertIn(
            '@router.get("/fleet-intelligence/snapshots/{snapshot_id}")',
            source,
        )
        self.assertIn("state_hash", source)

    def test_fleet_section_is_truth_blind_and_telemetry_blind(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        phase_section = source.split(
            "# Phase 7.0 — Fleet State & Decision Intelligence",
            1,
        )[1]

        resolver = phase_section.split(
            "def _current_fleet_decision_records(",
            1,
        )[1].split(
            "def _fleet_decision_snapshot_payload(",
            1,
        )[0]

        self.assertNotIn(
            "FailureEvent",
            resolver,
        )
        self.assertNotIn(
            "Telemetry.",
            resolver,
        )

        self.assertIn(
            '"usesTelemetry": False',
            phase_section,
        )
        self.assertIn(
            '"usesPrivateFailureTruth": False',
            phase_section,
        )

    def test_fleet_section_uses_current_predictions_and_prognostics(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = source.split(
            "# Phase 7.0 — Fleet State & Decision Intelligence",
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]
        self.assertIn("DiagnosticPrediction", section)
        self.assertIn("_current_prognostic_records", section)
        self.assertIn("DiagnosticAutomationAction", section)

    def test_ui_exposes_decision_queue_coverage_scenario_and_snapshots(self):
        source = (ROOT / "web/src/FleetDecisionIntelligence.tsx").read_text()
        for phrase in (
            "DECISION QUEUE",
            "COVERAGE DEBT",
            "WORKFLOW SCENARIO LAB",
            "DECISION CHECKPOINTS",
        ):
            self.assertIn(phrase, source)

    def test_ui_labels_attention_as_not_physical_risk(self):
        source = (ROOT / "web/src/FleetDecisionIntelligence.tsx").read_text()
        self.assertIn("NOT PHYSICAL RISK", source)
        self.assertIn("not failure probabilities", " ".join(source.split()))

    def test_ui_scenario_is_explicitly_no_write(self):
        source = (ROOT / "web/src/FleetDecisionIntelligence.tsx").read_text()
        self.assertIn("Run no-write scenario", source)
        self.assertIn("No-write counterfactual workflow simulation", source)

    def test_root_cause_mount_order(self):
        source = (ROOT / "web/src/RootCauseDashboard.tsx").read_text()
        automation_at = source.index("<OperationalAutomationIntelligence")
        fleet_at = source.index("<FleetDecisionIntelligence")
        transition_at = source.index("<DiagnosticTransitionIntelligence")
        self.assertLess(automation_at, fleet_at)
        self.assertLess(fleet_at, transition_at)

    def test_phase_does_not_train_or_modify_benchmark(self):
        api = (ROOT / "services/api/app/diagnostics.py").read_text()
        section = api.split(
            "# Phase 7.0 — Fleet State & Decision Intelligence",
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]
        rules = (
            ROOT
            / "services/common/fleetmind_common/fleet_decision_rules.py"
        ).read_text()
        combined = section + rules
        self.assertNotIn("xgboost.train", combined)
        self.assertNotIn("DiagnosticBenchmarkSnapshot", section)

    def test_snapshot_interpretation_does_not_rewrite_source_evidence(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn(
            "does not rewrite predictions, replay, events, episodes, cases",
            " ".join(source.split()),
        )


if __name__ == "__main__":
    unittest.main()
