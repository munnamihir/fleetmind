from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class FleetIntelligencePlanningContractTests(unittest.TestCase):

    def api(self):
        return (
            ROOT / "services/api/app/diagnostics.py"
        ).read_text()

    def rules(self):
        return (
            ROOT
            / "services/common/fleetmind_common/fleet_twin_rules.py"
        ).read_text()

    def test_phase_72_versioned(self):
        self.assertIn(
            'FLEET_TWIN_RULES_VERSION = "fm-fleet-twin-7.2-v1"',
            self.rules(),
        )

    def test_phase_72_routes(self):
        source = self.api()

        for route in (
            '@router.get("/fleet-twin/summary")',
            '@router.get("/fleet-twin/cohorts")',
            '@router.get("/fleet-twin/exposure")',
            '@router.get("/fleet-twin/exposure/compare")',
        ):
            self.assertIn(route, source)

    def test_selected_run_semantics(self):
        source = self.api()

        start = source.index(
            "def _current_fleet_twin_records("
        )
        end = source.index(
            '\n@router.get("/fleet-twin/summary")',
            start,
        )
        section = source[start:end]

        self.assertIn(
            "_resolve_vehicle_twin_run(db, run_id)",
            section,
        )
        self.assertIn(
            "selected_run=run",
            section,
        )
        self.assertNotIn(
            "_require_current_run(",
            section,
        )

    def test_bulk_anchor_bounded_context(self):
        source = self.api()

        start = source.index(
            "def _fleet_twin_scoring_context_by_vehicle("
        )
        end = source.index(
            "\ndef _current_fleet_twin_records(",
            start,
        )
        section = source[start:end]

        self.assertIn(
            "func.row_number()",
            section,
        )
        self.assertIn(
            "Telemetry.timestamp <= "
            "DiagnosticPrediction.anchor_timestamp",
            section,
        )
        self.assertIn(
            "DiagnosticPrediction.run_id == run.id",
            section,
        )
        self.assertIn(
            "DiagnosticPrediction.experiment_id == experiment_id",
            section,
        )

    def test_cohort_metadata_uses_frozen_context(self):
        source = self.api()

        for field in (
            '"model"',
            '"factory"',
            '"firmware"',
            '"pumpRevision"',
            '"scoringContextMileage"',
            '"scoringContextTimestamp"',
        ):
            self.assertIn(field, source)

    def test_count_and_rate_both_exposed(self):
        source = self.rules()

        for field in (
            '"populationCount"',
            '"nonHealthyCount"',
            '"nonHealthyRatePct"',
            '"caseCount"',
            '"caseRatePct"',
            '"coverageGapVehicleCount"',
            '"coverageGapRatePct"',
            '"workloadUnitsPer100Vehicles"',
        ):
            self.assertIn(field, source)

    def test_rate_ratio_not_physical_risk(self):
        source = self.api()

        self.assertIn(
            '"relativeFailureRisk": False',
            source,
        )
        self.assertIn(
            '"physicalFailureProbability": False',
            source,
        )

    def test_workload_not_technician_hours(self):
        source = self.api()

        self.assertIn(
            '"technicianHours": False',
            source,
        )

    def test_no_private_truth(self):
        source = self.api()

        start = source.index(
            "# Phase 7.2 — Fleet Twin + Normalized Cohort Exposure"
        )
        end = source.index(
            '@router.get("/summary")',
            start,
        )
        section = source[start:end]

        self.assertNotIn("FailureEvent", section)
        self.assertIn(
            '"usesPrivateFailureTruth": False',
            section,
        )

    def test_no_training_or_benchmark_mutation(self):
        source = self.api()

        start = source.index(
            "# Phase 7.2 — Fleet Twin + Normalized Cohort Exposure"
        )
        end = source.index(
            '@router.get("/summary")',
            start,
        )
        section = source[start:end]

        self.assertNotIn("xgboost.train", section)
        self.assertIn('"modelRetrained": False', section)
        self.assertIn('"benchmarkModified": False', section)


    # Phase 7.3 — Fleet State Change Intelligence

    def test_phase_73_versioned(self):
        rules = (
            ROOT
            / "services/common/fleetmind_common/fleet_change_rules.py"
        ).read_text()

        self.assertIn(
            'FLEET_CHANGE_RULES_VERSION = "fm-fleet-change-7.3-v1"',
            rules,
        )

    def test_phase_73_routes(self):
        source = self.api()

        for route in (
            '@router.get("/fleet-change/snapshots")',
            '@router.get("/fleet-change/compare")',
            '@router.get("/fleet-change/vehicles")',
        ):
            self.assertIn(route, source)

    def test_phase_73_reuses_existing_snapshot_model(self):
        source = self.api()

        self.assertIn(
            "DiagnosticFleetDecisionSnapshot",
            source,
        )

        store = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_store.py"
        ).read_text()

        self.assertNotIn(
            "DiagnosticFleetChangeSnapshot",
            store,
        )

    def test_phase_73_selected_run_safe(self):
        source = self.api()

        start = source.index(
            "def _fleet_change_inputs("
        )
        end = source.index(
            '@router.get("/fleet-change/snapshots")',
            start,
        )
        section = source[start:end]

        self.assertIn(
            "_resolve_vehicle_twin_run(",
            section,
        )
        self.assertIn(
            "selected_run=run",
            section,
        )
        self.assertNotIn(
            "_require_current_run(",
            section,
        )

    def test_phase_73_comparison_is_no_write(self):
        source = self.api()

        start = source.index(
            "# Phase 7.3 — Fleet State Change Intelligence"
        )
        end = source.index(
            '@router.get("/summary")',
            start,
        )
        section = source[start:end]

        self.assertIn(
            '"comparisonWrites": False',
            section,
        )
        self.assertNotIn(
            "db.commit()",
            section,
        )

    def test_phase_73_not_physical_condition_change(self):
        source = self.api()

        self.assertIn(
            '"physicalConditionChange": False',
            source,
        )
        self.assertIn(
            '"causalMaintenanceEffect": False',
            source,
        )
        self.assertIn(
            '"reliabilityChangeProof": False',
            source,
        )



    # Phase 7.4 — Capacity & Maintenance Planning Simulator

    def test_phase_74_versioned(self):
        rules = (
            ROOT
            / "services/common/fleetmind_common/capacity_planning_rules.py"
        ).read_text()

        self.assertIn(
            'CAPACITY_PLANNING_RULES_VERSION = '
            '"fm-capacity-planning-7.4-v1"',
            rules,
        )

    def test_phase_74_routes(self):
        source = self.api()

        self.assertIn(
            '@router.get("/capacity-planning/strategies")',
            source,
        )
        self.assertIn(
            '@router.post("/capacity-planning/simulate")',
            source,
        )

    def test_phase_74_uses_selected_fleet_twin_population(self):
        source = self.api()

        start = source.index(
            "def capacity_planning_simulate("
        )
        end = source.index(
            '\n@router.get("/summary")',
            start,
        )
        section = source[start:end]

        self.assertIn(
            "_current_fleet_twin_records(",
            section,
        )
        self.assertNotIn(
            "_require_current_run(",
            section,
        )

    def test_phase_74_no_write(self):
        source = self.api()

        start = source.index(
            "# Phase 7.4 — Capacity & Maintenance Planning Simulator"
        )
        end = source.index(
            '@router.get("/summary")',
            start,
        )
        section = source[start:end]

        self.assertIn(
            '"simulationWrites": False',
            section,
        )
        self.assertNotIn(
            "db.commit()",
            section,
        )
        self.assertNotIn(
            "db.add(",
            section,
        )

    def test_phase_74_no_automatic_execution(self):
        source = self.api()

        self.assertIn(
            '"automaticExecution": False',
            source,
        )
        self.assertIn(
            '"automaticScheduling": False',
            source,
        )

    def test_phase_74_units_not_hours(self):
        source = self.api()

        self.assertIn(
            '"technicianHours": False',
            source,
        )
        self.assertIn(
            '"physicalServiceDuration": False',
            source,
        )

    def test_phase_74_not_physical_outcome_prediction(self):
        source = self.api()

        self.assertIn(
            '"physicalOutcomePrediction": False',
            source,
        )
        self.assertIn(
            '"physicalRiskReduction": False',
            source,
        )
        self.assertIn(
            '"causalMaintenanceEffect": False',
            source,
        )



    # Phase 7.5 — Policy & Workflow Effectiveness

    def test_phase_75_versioned(self):
        rules = (
            ROOT
            / "services/common/fleetmind_common/"
            "workflow_effectiveness_rules.py"
        ).read_text()

        self.assertIn(
            'WORKFLOW_EFFECTIVENESS_RULES_VERSION =',
            rules,
        )
        self.assertIn(
            '"fm-workflow-effectiveness-7.5-v1"',
            rules,
        )

    def test_phase_75_routes(self):
        source = self.api()

        self.assertIn(
            '@router.get("/workflow-effectiveness/summary")',
            source,
        )
        self.assertIn(
            '@router.get("/workflow-effectiveness/policies")',
            source,
        )
        self.assertIn(
            '"/workflow-effectiveness/policies/{policy_key}"',
            source,
        )

    def test_phase_75_selected_run_safe(self):
        source = self.api()

        start = source.index(
            "def _workflow_effectiveness_inputs("
        )
        end = source.index(
            '@router.get("/workflow-effectiveness/summary")',
            start,
        )
        section = source[start:end]

        self.assertIn(
            "_resolve_vehicle_twin_run(",
            section,
        )
        self.assertIn(
            "selected_run=run",
            section,
        )
        self.assertNotIn(
            "_require_current_run(",
            section,
        )

    def test_phase_75_reads_persisted_lifecycle_timestamps(self):
        source = self.api()

        for field in (
            "row.created_at",
            "row.approved_at",
            "row.rejected_at",
            "row.executed_at",
        ):
            self.assertIn(field, source)

    def test_phase_75_no_write(self):
        source = self.api()

        start = source.index(
            "# Phase 7.5 — Policy & Workflow Effectiveness"
        )
        end = source.index(
            '@router.get("/summary")',
            start,
        )
        section = source[start:end]

        self.assertIn(
            '"analysisWrites": False',
            section,
        )
        self.assertNotIn(
            "db.commit()",
            section,
        )
        self.assertNotIn(
            "db.add(",
            section,
        )

    def test_phase_75_no_causal_claim(self):
        source = self.api()

        self.assertIn(
            '"causalAttribution": False',
            source,
        )
        self.assertIn(
            '"physicalMaintenanceEffectiveness": False',
            source,
        )
        self.assertIn(
            '"failurePreventionClaim": False',
            source,
        )
        self.assertIn(
            '"reliabilityImprovementClaim": False',
            source,
        )

    def test_phase_75_uses_current_workflow_target_only(self):
        source = self.api()

        self.assertIn(
            '"usesCurrentWorkflowMetadata": True',
            source,
        )
        self.assertIn(
            '"postRunTelemetryUsed": False',
            source,
        )

    def test_phase_75_does_not_retrain_or_modify_benchmark(self):
        source = self.api()

        self.assertIn(
            '"modelRetrained": False',
            source,
        )
        self.assertIn(
            '"benchmarkModified": False',
            source,
        )



    # Combined Phase 7.2–7.5 UI

    def test_combined_suite_ui_exists(self):
        ui = (
            ROOT
            / "web/src/FleetIntelligencePlanning.tsx"
        ).read_text()

        self.assertIn(
            "FLEET INTELLIGENCE & PLANNING",
            ui,
        )

    def test_combined_suite_four_workspaces(self):
        ui = (
            ROOT
            / "web/src/FleetIntelligencePlanning.tsx"
        ).read_text()

        for label in (
            "FLEET EXPOSURE",
            "STATE CHANGE",
            "CAPACITY PLANNING",
            "POLICY EFFECTIVENESS",
        ):
            self.assertIn(label, ui)

    def test_combined_suite_mount_order(self):
        source = (
            ROOT
            / "web/src/RootCauseDashboard.tsx"
        ).read_text()

        self.assertLess(
            source.index("<VehicleOperationalTwin"),
            source.index("<FleetIntelligencePlanning"),
        )

        self.assertLess(
            source.index("<FleetIntelligencePlanning"),
            source.index(
                "<DiagnosticTransitionIntelligence"
            ),
        )

    def test_combined_suite_selected_run_propagated(self):
        source = (
            ROOT
            / "web/src/RootCauseDashboard.tsx"
        ).read_text()

        self.assertIn(
            "<FleetIntelligencePlanning "
            "runId={status?.runId} />",
            source,
        )

    def test_combined_suite_count_rate_boundary(self):
        ui = (
            ROOT
            / "web/src/FleetIntelligencePlanning.tsx"
        ).read_text()

        self.assertIn(
            "Count is not rate. Rate is not physical risk.",
            ui,
        )

    def test_combined_suite_capacity_no_write_language(self):
        ui = (
            ROOT
            / "web/src/FleetIntelligencePlanning.tsx"
        ).read_text()

        self.assertIn(
            "Run no-write simulation",
            ui,
        )
        self.assertIn(
            "not technician hours",
            ui,
        )

    def test_combined_suite_effectiveness_non_causal(self):
        ui = (
            ROOT
            / "web/src/FleetIntelligencePlanning.tsx"
        ).read_text()

        self.assertIn(
            "does not prove that the",
            ui,
        )
        self.assertIn(
            "improved reliability",
            ui,
        )

    def test_combined_suite_no_private_truth_claim(self):
        ui = (
            ROOT
            / "web/src/FleetIntelligencePlanning.tsx"
        ).read_text()

        self.assertIn(
            "private failure truth excluded",
            ui,
        )



if __name__ == "__main__":
    unittest.main()
