from __future__ import annotations

import unittest

from services.common.fleetmind_common.fleet_decision_rules import (
    DECISION_STATE_NOMINAL,
    DECISION_STATE_PLAN,
    DECISION_STATE_WORKFLOW_ACTIVE,
    GAP_PENDING_AUTOMATION_APPROVAL,
    GAP_PRIORITY_CASE_WITHOUT_PLAN,
    FLEET_DECISION_RULES_VERSION,
    apply_workflow_scenario,
    derive_fleet_decision,
    summarize_fleet_records,
)


def base_record(**overrides):
    record = {
        "vehicleId": "EV-TEST",
        "topClass": "healthy",
        "topConfidence": 0.95,
        "caseId": None,
        "caseStatus": None,
        "reviewPriority": None,
        "assignedTo": None,
        "episodeState": None,
        "maintenanceTier": None,
        "maintenancePlanState": None,
        "watchlisted": False,
        "trajectoryEligible": None,
        "automationStatuses": [],
        "pendingActionTypes": [],
    }
    record.update(overrides)
    return record


class FleetDecisionRulesTests(unittest.TestCase):
    def test_version(self):
        self.assertEqual(
            FLEET_DECISION_RULES_VERSION,
            "fm-fleet-decision-7.0-v1",
        )

    def test_healthy_vehicle_is_nominal(self):
        result = derive_fleet_decision(base_record())
        self.assertEqual(result["decisionState"], DECISION_STATE_NOMINAL)
        self.assertEqual(result["coverageGaps"], [])
        self.assertEqual(result["workloadUnits"], 0.0)

    def test_priority_case_without_plan_is_plan_state_and_gap(self):
        result = derive_fleet_decision(
            base_record(
                topClass="inverter",
                topConfidence=0.91,
                caseId=7,
                caseStatus="OPEN",
                reviewPriority="MEDIUM",
                assignedTo="mihir",
                episodeState="EVOLVING",
                maintenanceTier="PLAN_SERVICE",
                trajectoryEligible=True,
            )
        )
        self.assertEqual(result["decisionState"], DECISION_STATE_PLAN)
        self.assertIn(
            GAP_PRIORITY_CASE_WITHOUT_PLAN,
            result["coverageGaps"],
        )

    def test_existing_plan_moves_to_workflow_active(self):
        result = derive_fleet_decision(
            base_record(
                topClass="inverter",
                topConfidence=0.91,
                caseId=7,
                caseStatus="OPEN",
                reviewPriority="MEDIUM",
                assignedTo="mihir",
                episodeState="EVOLVING",
                maintenanceTier="PLAN_SERVICE",
                maintenancePlanState="REVIEW",
                trajectoryEligible=True,
            )
        )
        self.assertEqual(
            result["decisionState"],
            DECISION_STATE_WORKFLOW_ACTIVE,
        )
        self.assertNotIn(
            GAP_PRIORITY_CASE_WITHOUT_PLAN,
            result["coverageGaps"],
        )

    def test_pending_approval_is_coverage_debt(self):
        result = derive_fleet_decision(
            base_record(
                topClass="traction_motor",
                topConfidence=0.8,
                caseId=9,
                caseStatus="OPEN",
                reviewPriority="MEDIUM",
                assignedTo=None,
                episodeState="EVOLVING",
                maintenanceTier="PLAN_SERVICE",
                trajectoryEligible=True,
                automationStatuses=["PENDING_APPROVAL"],
                pendingActionTypes=["ENSURE_REVIEW_PLAN"],
            )
        )
        self.assertIn(
            GAP_PENDING_AUTOMATION_APPROVAL,
            result["coverageGaps"],
        )

    def test_execute_pending_scenario_is_no_write_transform(self):
        original = derive_fleet_decision(
            base_record(
                topClass="traction_motor",
                topConfidence=0.8,
                caseId=9,
                caseStatus="OPEN",
                reviewPriority="MEDIUM",
                assignedTo="mihir",
                episodeState="EVOLVING",
                maintenanceTier="PLAN_SERVICE",
                trajectoryEligible=True,
                automationStatuses=["PENDING_APPROVAL"],
                pendingActionTypes=["ENSURE_REVIEW_PLAN"],
            )
        )
        projected = apply_workflow_scenario(
            original,
            "EXECUTE_PENDING_WORKFLOW_ACTIONS",
        )
        self.assertIsNone(original["maintenancePlanState"])
        self.assertEqual(projected["maintenancePlanState"], "REVIEW")
        self.assertEqual(
            projected["decisionState"],
            DECISION_STATE_WORKFLOW_ACTIVE,
        )

    def test_assign_scenario_clears_unassigned_gap_only_in_projection(self):
        original = derive_fleet_decision(
            base_record(
                topClass="battery_pack",
                topConfidence=0.9,
                caseId=10,
                caseStatus="OPEN",
                reviewPriority="LOW",
                assignedTo=None,
                episodeState="EVOLVING",
                maintenanceTier="MONITOR",
                trajectoryEligible=True,
            )
        )
        projected = apply_workflow_scenario(
            original,
            "ASSIGN_UNASSIGNED_CASES",
        )
        self.assertIsNone(original["assignedTo"])
        self.assertEqual(projected["assignedTo"], "scenario_operator")
        self.assertLess(
            projected["workloadUnits"],
            original["workloadUnits"],
        )

    def test_close_all_workflow_gaps_adds_plan_and_assignment(self):
        original = derive_fleet_decision(
            base_record(
                topClass="coolant_pump",
                topConfidence=0.95,
                caseId=12,
                caseStatus="OPEN",
                reviewPriority="HIGH",
                assignedTo=None,
                episodeState="DESTABILIZED",
                maintenanceTier="URGENT_REVIEW",
                trajectoryEligible=True,
            )
        )
        projected = apply_workflow_scenario(
            original,
            "CLOSE_ALL_WORKFLOW_GAPS",
        )
        self.assertEqual(projected["maintenancePlanState"], "REVIEW")
        self.assertEqual(projected["assignedTo"], "scenario_operator")
        self.assertTrue(projected["watchlisted"])

    def test_summary_counts_states_and_gaps(self):
        records = [
            derive_fleet_decision(base_record(vehicleId="EV-1")),
            derive_fleet_decision(
                base_record(
                    vehicleId="EV-2",
                    topClass="inverter",
                    topConfidence=0.9,
                    caseId=1,
                    reviewPriority="MEDIUM",
                    assignedTo="mihir",
                    episodeState="EVOLVING",
                    maintenanceTier="PLAN_SERVICE",
                    trajectoryEligible=True,
                )
            ),
        ]
        summary = summarize_fleet_records(records)
        self.assertEqual(summary["totalVehicles"], 2)
        self.assertEqual(summary["nonHealthyHypotheses"], 1)
        self.assertEqual(summary["attentionRequired"], 1)
        self.assertGreater(summary["coverageGapInstances"], 0)

    def test_attention_score_is_bounded(self):
        result = derive_fleet_decision(
            base_record(
                topClass="inverter",
                topConfidence=1.0,
                caseId=1,
                reviewPriority="HIGH",
                assignedTo=None,
                episodeState="DESTABILIZED",
                maintenanceTier="URGENT_REVIEW",
                trajectoryEligible=False,
                automationStatuses=["PENDING_APPROVAL"],
                pendingActionTypes=["ENSURE_REVIEW_PLAN"],
            )
        )
        self.assertGreaterEqual(result["attentionScore"], 0.0)
        self.assertLessEqual(result["attentionScore"], 100.0)


if __name__ == "__main__":
    unittest.main()
