from __future__ import annotations

import unittest

from fleetmind_common.fleet_change_rules import (
    FLEET_CHANGE_RULES_VERSION,
    compare_fleet_states,
    vehicle_state_change,
)


class FleetChangeRulesMathTests(unittest.TestCase):

    def base(self):
        return {
            "vehicleId": "EV-1",
            "topClass": "inverter",
            "topConfidence": 0.8,
            "decisionState": "PLAN",
            "attentionScore": 60.0,
            "workloadUnits": 2.5,
            "caseId": 1,
            "caseStatus": "OPEN",
            "reviewPriority": "MEDIUM",
            "episodeId": 2,
            "episodeState": "EVOLVING",
            "maintenanceTier": "PLAN_SERVICE",
            "maintenancePlanId": None,
            "maintenancePlanState": None,
            "assignedTo": None,
            "watchlisted": False,
            "trajectoryEligible": True,
            "automationStatuses": ["PENDING_APPROVAL"],
            "pendingActionTypes": ["ENSURE_REVIEW_PLAN"],
            "coverageGaps": [
                "UNASSIGNED_CASE",
                "PRIORITY_CASE_WITHOUT_PLAN",
            ],
        }

    def test_version(self):
        self.assertEqual(
            FLEET_CHANGE_RULES_VERSION,
            "fm-fleet-change-7.3-v1",
        )

    def test_identical_state_unchanged(self):
        row = self.base()
        result = vehicle_state_change(row, dict(row))

        self.assertFalse(result["changed"])
        self.assertEqual(result["transitions"], [])

    def test_new_attention(self):
        before = dict(self.base())
        before["decisionState"] = "NOMINAL"

        after = dict(self.base())
        after["decisionState"] = "OBSERVE"

        result = vehicle_state_change(before, after)

        self.assertIn("NEW_ATTENTION", result["transitions"])

    def test_resolved_attention(self):
        before = dict(self.base())
        before["decisionState"] = "OBSERVE"

        after = dict(self.base())
        after["decisionState"] = "NOMINAL"

        result = vehicle_state_change(before, after)

        self.assertIn(
            "RESOLVED_ATTENTION",
            result["transitions"],
        )

    def test_escalated(self):
        before = dict(self.base())
        before["decisionState"] = "OBSERVE"

        after = dict(self.base())
        after["decisionState"] = "PLAN"

        result = vehicle_state_change(before, after)

        self.assertIn("ESCALATED", result["transitions"])

    def test_workflow_started_and_plan_added(self):
        before = self.base()

        after = dict(before)
        after["decisionState"] = "WORKFLOW_ACTIVE"
        after["maintenancePlanId"] = 10
        after["maintenancePlanState"] = "REVIEW"

        result = vehicle_state_change(before, after)

        self.assertIn(
            "WORKFLOW_STARTED",
            result["transitions"],
        )
        self.assertIn("PLAN_ADDED", result["transitions"])

    def test_workflow_completed(self):
        before = self.base()
        before["maintenancePlanState"] = "SCHEDULED"

        after = dict(before)
        after["maintenancePlanState"] = "COMPLETED"

        result = vehicle_state_change(before, after)

        self.assertIn(
            "WORKFLOW_COMPLETED",
            result["transitions"],
        )

    def test_coverage_improved(self):
        before = self.base()

        after = dict(before)
        after["coverageGaps"] = ["UNASSIGNED_CASE"]

        result = vehicle_state_change(before, after)

        self.assertIn(
            "COVERAGE_IMPROVED",
            result["transitions"],
        )
        self.assertEqual(result["coverageGapDelta"], -1)

    def test_coverage_regressed(self):
        before = self.base()
        before["coverageGaps"] = []

        after = dict(before)
        after["coverageGaps"] = ["UNASSIGNED_CASE"]

        result = vehicle_state_change(before, after)

        self.assertIn(
            "COVERAGE_REGRESSED",
            result["transitions"],
        )
        self.assertEqual(result["coverageGapDelta"], 1)

    def test_automation_executed(self):
        before = self.base()

        after = dict(before)
        after["automationStatuses"] = ["EXECUTED"]

        result = vehicle_state_change(before, after)

        self.assertIn(
            "AUTOMATION_EXECUTED",
            result["transitions"],
        )

    def test_fleet_rollup_deltas(self):
        before = [self.base()]

        after_row = dict(self.base())
        after_row["workloadUnits"] = 1.25
        after_row["attentionScore"] = 40.0
        after_row["coverageGaps"] = []

        result = compare_fleet_states(
            before,
            [after_row],
        )

        self.assertEqual(result["vehiclesCompared"], 1)
        self.assertEqual(result["vehiclesChanged"], 1)
        self.assertEqual(result["workloadUnitsDelta"], -1.25)
        self.assertEqual(
            result["attentionScoreTotalDelta"],
            -20.0,
        )
        self.assertEqual(
            result["coverageGapInstanceDelta"],
            -2,
        )

    def test_transition_is_not_physical_claim(self):
        result = vehicle_state_change(
            self.base(),
            dict(self.base()),
        )

        text = result["interpretation"].lower()

        self.assertIn("operational", text)
        self.assertIn("not", text)
        self.assertIn("physical", text)


if __name__ == "__main__":
    unittest.main()
