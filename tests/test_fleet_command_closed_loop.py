import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DIAGNOSTICS = (
    ROOT
    / "services"
    / "api"
    / "app"
    / "diagnostics.py"
)


class EvidenceExplainabilityApiContractTests(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        cls.source = DIAGNOSTICS.read_text()

    def test_phase_76_rules_imported(self):
        self.assertIn(
            "evidence_explainability_rules import",
            self.source,
        )

    def test_phase_76_summary_route_exists(self):
        self.assertIn(
            '@router.get("/explainability/summary")',
            self.source,
        )

    def test_phase_76_vehicle_list_route_exists(self):
        self.assertIn(
            '@router.get("/explainability/vehicles")',
            self.source,
        )

    def test_phase_76_vehicle_detail_route_exists(self):
        self.assertIn(
            '"/explainability/vehicles/{vehicle_id}"',
            self.source,
        )

    def test_phase_76_attention_route_exists(self):
        self.assertIn(
            (
                '"/explainability/vehicles/'
                '{vehicle_id}/attention"'
            ),
            self.source,
        )

    def test_phase_76_lineage_route_exists(self):
        self.assertIn(
            (
                '"/explainability/vehicles/'
                '{vehicle_id}/lineage"'
            ),
            self.source,
        )

    def test_phase_76_fleet_reads_use_bulk_resolver(self):
        section = self.source.split(
            "# Phase 7.6 — Evidence & Explainability Center",
            1,
        )[1]

        self.assertGreaterEqual(
            section.count(
                "_current_fleet_twin_records("
            ),
            2,
        )

    def test_phase_76_is_selected_run_safe(self):
        section = self.source.split(
            "# Phase 7.6 — Evidence & Explainability Center",
            1,
        )[1]

        self.assertIn(
            '"selectedRunOnly": True',
            section,
        )

        self.assertIn(
            (
                '"activeTelemetryExperimentRequired": '
                "False"
            ),
            section,
        )

        self.assertIn(
            '"postRunTelemetryUsed": False',
            section,
        )

    def test_phase_76_rejects_shap_and_causality(self):
        section = self.source.split(
            "# Phase 7.6 — Evidence & Explainability Center",
            1,
        )[1]

        self.assertIn(
            '"shapValues": False',
            section,
        )

        self.assertIn(
            '"modelFeatureAttribution": False',
            section,
        )

        self.assertIn(
            '"causalAttribution": False',
            section,
        )

    def test_phase_76_has_no_write_routes(self):
        section = self.source.split(
            "# Phase 7.6 — Evidence & Explainability Center",
            1,
        )[1]

        self.assertNotIn(
            '@router.post("/explainability',
            section,
        )


if __name__ == "__main__":
    unittest.main()


class FleetCommandApiContractTests(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        cls.source = DIAGNOSTICS.read_text()

        cls.section = cls.source.split(
            "# Phase 7.7 — Fleet Command Center",
            1,
        )[1]

    def test_phase_77_rules_imported(self):
        self.assertIn(
            "fleet_command_rules import",
            self.source,
        )

    def test_phase_77_summary_route(self):
        self.assertIn(
            '@router.get("/fleet-command/summary")',
            self.section,
        )

    def test_phase_77_queues_route(self):
        self.assertIn(
            '@router.get("/fleet-command/queues")',
            self.section,
        )

    def test_phase_77_vehicles_route(self):
        self.assertIn(
            '@router.get("/fleet-command/vehicles")',
            self.section,
        )

    def test_phase_77_cohorts_route(self):
        self.assertIn(
            '@router.get("/fleet-command/cohorts")',
            self.section,
        )

    def test_phase_77_uses_bulk_fleet_resolver(self):
        self.assertGreaterEqual(
            self.section.count(
                "_current_fleet_twin_records("
            ),
            4,
        )

    def test_phase_77_reuses_phase_72_exposure(self):
        self.assertIn(
            "cohort_exposure_rows(",
            self.section,
        )

        self.assertIn(
            "exposure_measure_rate(",
            self.section,
        )

        self.assertIn(
            "fleet_exposure_summary(",
            self.section,
        )

    def test_phase_77_reuses_phase_75_effectiveness(self):
        self.assertIn(
            "workflow_effectiveness_summary(",
            self.section,
        )

    def test_phase_77_reuses_phase_76_explanation(self):
        self.assertIn(
            "summarize_attention_explanations(",
            self.section,
        )

    def test_phase_77_selected_run_safe(self):
        self.assertIn(
            '"selectedRunOnly": True',
            self.section,
        )

        self.assertIn(
            (
                '"activeTelemetryExperimentRequired": '
                "False"
            ),
            self.section,
        )

        self.assertIn(
            '"postRunTelemetryUsed": False',
            self.section,
        )

    def test_phase_77_read_only(self):
        self.assertIn(
            '"writes": False',
            self.section,
        )

        self.assertNotIn(
            '@router.post("/fleet-command',
            self.section,
        )

    def test_phase_77_rejects_physical_meaning(self):
        self.assertIn(
            '"queuePriorityIsPhysicalRisk": False',
            self.section,
        )

        self.assertIn(
            '"physicalFailureProbability": False',
            self.section,
        )

        self.assertIn(
            '"physicalConditionProof": False',
            self.section,
        )

        self.assertIn(
            '"causalAttribution": False',
            self.section,
        )


if __name__ == "__main__":
    unittest.main()


STORE = (
    ROOT
    / "services"
    / "common"
    / "fleetmind_common"
    / "diagnostic_store.py"
)


class ClosedLoopPersistenceContractTests(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        cls.api = DIAGNOSTICS.read_text()
        cls.store = STORE.read_text()

        cls.section = cls.api.split(
            (
                "# Phase 8.0 — Closed-Loop "
                "Operations Foundation"
            ),
            1,
        )[1]

    def test_phase_80_recommendation_table(self):
        self.assertIn(
            (
                'class '
                'DiagnosticOperationalRecommendation'
                '(Base):'
            ),
            self.store,
        )

        self.assertIn(
            (
                '__tablename__ = '
                '"diagnostic_operational_recommendations"'
            ),
            self.store,
        )

    def test_phase_80_activity_table(self):
        self.assertIn(
            (
                'class '
                'DiagnosticOperationalRecommendationActivity'
                '(Base):'
            ),
            self.store,
        )

        self.assertIn(
            (
                '"diagnostic_operational_'
                'recommendation_activities"'
            ),
            self.store,
        )

    def test_phase_80_unique_materialization_key(self):
        self.assertIn(
            (
                '"uq_diagnostic_operational_"'
            ),
            self.store,
        )

        self.assertIn(
            "recommendation_key",
            self.store,
        )

    def test_phase_80_evaluate_route(self):
        self.assertIn(
            (
                '"/closed-loop/'
                'recommendations/evaluate"'
            ),
            self.section,
        )

    def test_phase_80_list_route(self):
        self.assertIn(
            (
                '"/closed-loop/'
                'recommendations"'
            ),
            self.section,
        )

    def test_phase_80_detail_route(self):
        self.assertIn(
            (
                '"/closed-loop/recommendations/'
                '{recommendation_id}"'
            ),
            self.section,
        )

    def test_phase_80_explicit_approval_chain_routes(self):
        for route in (
            "/acknowledge",
            "/request-approval",
            "/approve",
            "/mark-execution-ready",
            "/execute",
        ):
            self.assertIn(
                route,
                self.section,
            )

    def test_phase_80_terminal_exit_routes(self):
        for route in (
            "/reject",
            "/cancel",
            "/supersede",
        ):
            self.assertIn(
                route,
                self.section,
            )

    def test_phase_80_evaluation_defaults_to_preview(self):
        self.assertIn(
            "materialize: bool = False",
            self.section,
        )

    def test_phase_80_bulk_idempotency_lookup(self):
        self.assertIn(
            (
                "DiagnosticOperationalRecommendation."
                "recommendation_key.in_("
            ),
            self.section,
        )

    def test_phase_80_records_created_activity(self):
        self.assertIn(
            'activity_type="CREATED"',
            self.section,
        )

        self.assertIn(
            "from_state=None",
            self.section,
        )

        self.assertIn(
            "to_state=STATE_PROPOSED",
            self.section,
        )

    def test_phase_80_transition_uses_canonical_rules(self):
        self.assertIn(
            "require_transition(",
            self.section,
        )

    def test_phase_80_repeated_target_is_idempotent(self):
        self.assertIn(
            (
                "if current_state "
                "== target_state:"
            ),
            self.section,
        )

        self.assertIn(
            "return False",
            self.section,
        )

    def test_phase_80_selected_run_safe(self):
        self.assertIn(
            (
                "_resolve_vehicle_twin_run("
            ),
            self.section,
        )

        self.assertIn(
            (
                "_current_fleet_twin_records("
            ),
            self.section,
        )

    def test_phase_80_private_truth_excluded(self):
        self.assertIn(
            (
                '"usesPrivateFailureTruth": '
                "False"
            ),
            self.section,
        )

        self.assertIn(
            (
                '"failureMarkersExposed": '
                "False"
            ),
            self.section,
        )

    def test_phase_80_no_automatic_approval_or_execution(self):
        self.assertIn(
            '"automaticApproval": False',
            self.section,
        )

        self.assertIn(
            '"automaticExecution": False',
            self.section,
        )

    def test_phase_80_no_physical_action(self):
        self.assertIn(
            '"physicalAction": False',
            self.section,
        )

        self.assertIn(
            '"vehicleActuation": False',
            self.section,
        )

        self.assertIn(
            (
                '"physicalRepairConfirmation": '
                "False"
            ),
            self.section,
        )


if __name__ == "__main__":
    unittest.main()


class DecisionQueueApiContractTests(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        cls.api = DIAGNOSTICS.read_text()
        cls.store = STORE.read_text()

        cls.section = cls.api.split(
            (
                "# Phase 8.1 — Decision Queue "
                "& Approval Orchestration"
            ),
            1,
        )[1]

    def test_phase_81_assignment_persisted(self):
        self.assertIn(
            "assigned_to: Mapped[str | None]",
            self.store,
        )

        self.assertIn(
            "assigned_at: Mapped[datetime | None]",
            self.store,
        )

    def test_phase_81_rules_imported(self):
        self.assertIn(
            "decision_queue_rules import",
            self.api,
        )

    def test_phase_81_summary_route(self):
        self.assertIn(
            '@router.get("/decision-queue/summary")',
            self.section,
        )

    def test_phase_81_list_route(self):
        self.assertIn(
            '@router.get("/decision-queue")',
            self.section,
        )

    def test_phase_81_detail_route(self):
        self.assertIn(
            (
                '"/decision-queue/'
                '{recommendation_id}"'
            ),
            self.section,
        )

    def test_phase_81_assignment_route(self):
        self.assertIn(
            (
                '"/decision-queue/'
                '{recommendation_id}/assign"'
            ),
            self.section,
        )

    def test_phase_81_full_approval_chain(self):
        for route in (
            "/acknowledge",
            "/request-approval",
            "/approve",
            "/mark-execution-ready",
            "/execute",
        ):
            self.assertIn(
                route,
                self.section,
            )

    def test_phase_81_terminal_controls(self):
        for route in (
            "/reject",
            "/cancel",
            "/supersede",
        ):
            self.assertIn(
                route,
                self.section,
            )

    def test_phase_81_reuses_canonical_queue_rules(self):
        self.assertIn(
            "decision_queue_summary(",
            self.section,
        )

        self.assertIn(
            "decision_queue_rows(",
            self.section,
        )

    def test_phase_81_reuses_closed_loop_transition_gate(self):
        self.assertIn(
            "_closed_loop_transition_response(",
            self.section,
        )

    def test_phase_81_assignment_respects_terminal_state(self):
        self.assertIn(
            "assignment_allowed(",
            self.section,
        )

        self.assertIn(
            "terminal lifecycle state",
            self.section,
        )

    def test_phase_81_assignment_activity_is_audited(self):
        self.assertIn(
            '"ASSIGNED"',
            self.section,
        )

        self.assertIn(
            '"UNASSIGNED"',
            self.section,
        )

        self.assertIn(
            "previousAssignee",
            self.section,
        )

    def test_phase_81_assignment_is_idempotent(self):
        self.assertIn(
            "if previous == target:",
            self.section,
        )

        self.assertIn(
            '"changed": False',
            self.section,
        )

    def test_phase_81_payload_exposes_assignment(self):
        self.assertIn(
            '"assignedTo": row.assigned_to',
            self.api,
        )

        self.assertIn(
            '"assignedAt": (',
            self.api,
        )

    def test_phase_81_selected_run_safe(self):
        self.assertIn(
            "_resolve_vehicle_twin_run(",
            self.section,
        )

        self.assertIn(
            (
                '"selectedRunOnly": True'
            ),
            self.section,
        )

    def test_phase_81_no_automatic_operations(self):
        self.assertIn(
            '"automaticAssignment": False',
            self.section,
        )

        self.assertIn(
            '"automaticApproval": False',
            self.section,
        )

        self.assertIn(
            '"automaticExecution": False',
            self.section,
        )

    def test_phase_81_review_target_is_not_sla(self):
        self.assertIn(
            (
                '"reviewTargetIsSafetyDeadline": '
                "False"
            ),
            self.section,
        )

        self.assertIn(
            (
                '"reviewTargetIsContractualSla": '
                "False"
            ),
            self.section,
        )

    def test_phase_81_rejects_physical_semantics(self):
        self.assertIn(
            '"priorityIsPhysicalRisk": False',
            self.section,
        )

        self.assertIn(
            '"ageIsPhysicalCondition": False',
            self.section,
        )

        self.assertIn(
            '"physicalAction": False',
            self.section,
        )

        self.assertIn(
            '"vehicleActuation": False',
            self.section,
        )


if __name__ == "__main__":
    unittest.main()


FLEET_COMMAND_UI = (
    ROOT
    / "web"
    / "src"
    / "FleetCommandOperations.tsx"
)

ROOT_CAUSE_UI = (
    ROOT
    / "web"
    / "src"
    / "RootCauseDashboard.tsx"
)


class FleetCommandOperationsUiContractTests(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        cls.ui = (
            FLEET_COMMAND_UI.read_text()
        )

        cls.root = (
            ROOT_CAUSE_UI.read_text()
        )

    def test_combined_workspace_exists(self):
        self.assertIn(
            (
                "export function "
                "FleetCommandOperations"
            ),
            self.ui,
        )

    def test_four_workspaces_exist(self):
        for label in (
            "Command Center",
            "Explainability",
            "Decision Queue",
            "Closed Loop",
        ):
            self.assertIn(
                label,
                self.ui,
            )

    def test_command_center_api_used(self):
        self.assertIn(
            (
                "/api/v1/diagnostics/"
                "fleet-command/summary"
            ),
            self.ui,
        )

    def test_explainability_api_used(self):
        self.assertIn(
            (
                "/api/v1/diagnostics/"
                "explainability/summary"
            ),
            self.ui,
        )

    def test_decision_queue_api_used(self):
        self.assertIn(
            (
                "/api/v1/diagnostics/"
                "decision-queue/summary"
            ),
            self.ui,
        )

    def test_closed_loop_evaluation_used(self):
        self.assertIn(
            (
                "/api/v1/diagnostics/"
                "closed-loop/"
                "recommendations/evaluate"
            ),
            self.ui,
        )

    def test_materialization_is_explicit(self):
        self.assertIn(
            "Preview evaluation",
            self.ui,
        )

        self.assertIn(
            "Materialize recommendations",
            self.ui,
        )

    def test_actor_is_present_for_mutations(self):
        self.assertIn(
            "Required for every queue mutation.",
            self.ui,
        )

    def test_full_human_gate_is_visible(self):
        self.assertIn(
            (
                "PROPOSED → ACKNOWLEDGED "
                "→ APPROVAL REQUIRED "
                "→ APPROVED →"
            ),
            self.ui,
        )

        self.assertIn(
            "EXECUTION READY → EXECUTED",
            self.ui,
        )

    def test_ui_rejects_shap_claim(self):
        self.assertIn(
            "NOT SHAP",
            self.ui,
        )

    def test_ui_rejects_physical_risk(self):
        self.assertIn(
            "queue priority ≠ physical risk",
            self.ui,
        )

    def test_ui_rejects_physical_repair_claim(self):
        self.assertIn(
            "execution ≠ physical repair",
            self.ui,
        )

    def test_component_is_mounted(self):
        self.assertIn(
            (
                "import { FleetCommandOperations } "
                "from './FleetCommandOperations';"
            ),
            self.root,
        )

        self.assertIn(
            "<FleetCommandOperations",
            self.root,
        )

    def test_selected_run_propagated(self):
        self.assertIn(
            "runId={status?.runId}",
            self.root,
        )

    def test_vehicle_cross_navigation_connected(self):
        self.assertIn(
            (
                "onSelectVehicle="
                "{setSelectedVehicleId}"
            ),
            self.root,
        )


if __name__ == "__main__":
    unittest.main()


STYLES = (
    ROOT
    / "web"
    / "src"
    / "styles.css"
)


class FleetCommandOperationsCssContractTests(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        cls.styles = (
            STYLES.read_text()
        )

    def test_phase_76_81_css_section_exists(self):
        self.assertIn(
            (
                "Phases 7.6–8.1 — "
                "Fleet Command & Operations"
            ),
            self.styles,
        )

    def test_command_workspace_styled(self):
        self.assertIn(
            ".fleetCommandOperations",
            self.styles,
        )

        self.assertIn(
            ".fleetOpsWorkspace",
            self.styles,
        )

    def test_four_tab_workspace_styled(self):
        self.assertIn(
            ".fleetOpsTabs",
            self.styles,
        )

        self.assertIn(
            ".fleetOpsTab.active",
            self.styles,
        )

    def test_explainability_styled(self):
        self.assertIn(
            ".fleetOpsExplainGrid",
            self.styles,
        )

        self.assertIn(
            ".fleetOpsComponentRow",
            self.styles,
        )

        self.assertIn(
            ".fleetOpsLineagePath",
            self.styles,
        )

    def test_decision_queue_styled(self):
        self.assertIn(
            ".fleetOpsDecisionTable",
            self.styles,
        )

        self.assertIn(
            ".fleetOpsDecisionRow",
            self.styles,
        )

    def test_priority_indicators_styled(self):
        for priority in (
            "p0",
            "p1",
            "p2",
            "p3",
        ):
            self.assertIn(
                (
                    ".fleetOpsPriority."
                    f"priority-{priority}"
                ),
                self.styles,
            )

    def test_closed_loop_styled(self):
        self.assertIn(
            ".fleetOpsClosedLoopHero",
            self.styles,
        )

        self.assertIn(
            ".fleetOpsRecommendation",
            self.styles,
        )

        self.assertIn(
            ".fleetOpsGuardrail",
            self.styles,
        )

    def test_responsive_rules_exist(self):
        self.assertIn(
            "@media (max-width: 1050px)",
            self.styles,
        )

        self.assertIn(
            "@media (max-width: 800px)",
            self.styles,
        )

        self.assertIn(
            "@media (max-width: 570px)",
            self.styles,
        )


if __name__ == "__main__":
    unittest.main()
