import unittest

from fleetmind_common.fleet_command_rules import (
    FLEET_COMMAND_QUEUES,
    FLEET_COMMAND_RULES_VERSION,
    QUEUE_COVERAGE_GAPS,
    QUEUE_HIGHEST_ATTENTION,
    QUEUE_PENDING_APPROVAL,
    QUEUE_PLAN_SERVICE,
    QUEUE_TRAJECTORY_INELIGIBLE,
    QUEUE_UNASSIGNED_CASES,
    QUEUE_URGENT_REVIEW,
    command_center_summary,
    command_queue_record,
    command_queue_rows,
    command_vehicle_rows,
    queue_counts,
    queue_match,
)


class FleetCommandRulesMathTests(
    unittest.TestCase
):

    def _records(self):
        return [
            {
                "vehicleId": "EV-001",
                "topClass": "battery_pack",
                "topConfidence": 0.91,
                "decisionState": "PLAN",
                "attentionScore": 88.0,
                "workloadUnits": 3.0,
                "maintenanceTier": (
                    "URGENT_REVIEW"
                ),
                "reviewPriority": "HIGH",
                "caseId": 1,
                "assignedTo": None,
                "trajectoryEligible": False,
                "coverageGaps": [
                    "UNASSIGNED_CASE",
                    "TRAJECTORY_INELIGIBLE",
                    "PENDING_AUTOMATION_APPROVAL",
                ],
                "automationStatuses": [
                    "PENDING_APPROVAL",
                ],
                "automationStatus": (
                    "PENDING_APPROVAL"
                ),
            },
            {
                "vehicleId": "EV-002",
                "topClass": "inverter",
                "topConfidence": 0.82,
                "decisionState": "PLAN",
                "attentionScore": 72.0,
                "workloadUnits": 2.5,
                "maintenanceTier": (
                    "PLAN_SERVICE"
                ),
                "reviewPriority": "MEDIUM",
                "caseId": 2,
                "assignedTo": "operator-a",
                "trajectoryEligible": True,
                "coverageGaps": [],
                "automationStatuses": [],
                "automationStatus": None,
            },
            {
                "vehicleId": "EV-003",
                "topClass": "healthy",
                "topConfidence": 0.97,
                "decisionState": "NOMINAL",
                "attentionScore": 0.0,
                "workloadUnits": 0.0,
                "maintenanceTier": None,
                "caseId": None,
                "assignedTo": None,
                "trajectoryEligible": None,
                "coverageGaps": [],
                "automationStatuses": [],
                "automationStatus": None,
            },
        ]

    def test_rules_version(self):
        result = command_center_summary(
            self._records()
        )

        self.assertEqual(
            result["rulesVersion"],
            FLEET_COMMAND_RULES_VERSION,
        )

        self.assertEqual(
            result["rulesVersion"],
            "fm-fleet-command-7.7-v1",
        )

    def test_seven_command_queues(self):
        self.assertEqual(
            len(FLEET_COMMAND_QUEUES),
            7,
        )

    def test_highest_attention_queue(self):
        records = self._records()

        self.assertTrue(
            queue_match(
                records[0],
                QUEUE_HIGHEST_ATTENTION,
            )
        )

        self.assertFalse(
            queue_match(
                records[2],
                QUEUE_HIGHEST_ATTENTION,
            )
        )

    def test_urgent_review_queue(self):
        records = self._records()

        self.assertTrue(
            queue_match(
                records[0],
                QUEUE_URGENT_REVIEW,
            )
        )

        self.assertFalse(
            queue_match(
                records[1],
                QUEUE_URGENT_REVIEW,
            )
        )

    def test_plan_service_queue(self):
        records = self._records()

        self.assertTrue(
            queue_match(
                records[1],
                QUEUE_PLAN_SERVICE,
            )
        )

    def test_coverage_gap_queue(self):
        records = self._records()

        self.assertTrue(
            queue_match(
                records[0],
                QUEUE_COVERAGE_GAPS,
            )
        )

        self.assertFalse(
            queue_match(
                records[1],
                QUEUE_COVERAGE_GAPS,
            )
        )

    def test_pending_approval_queue(self):
        records = self._records()

        self.assertTrue(
            queue_match(
                records[0],
                QUEUE_PENDING_APPROVAL,
            )
        )

    def test_unassigned_case_queue(self):
        records = self._records()

        self.assertTrue(
            queue_match(
                records[0],
                QUEUE_UNASSIGNED_CASES,
            )
        )

        self.assertFalse(
            queue_match(
                records[1],
                QUEUE_UNASSIGNED_CASES,
            )
        )

    def test_trajectory_ineligible_queue(self):
        records = self._records()

        self.assertTrue(
            queue_match(
                records[0],
                QUEUE_TRAJECTORY_INELIGIBLE,
            )
        )

        self.assertFalse(
            queue_match(
                records[1],
                QUEUE_TRAJECTORY_INELIGIBLE,
            )
        )

    def test_unsupported_queue_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            queue_match(
                self._records()[0],
                "PHYSICAL_FAILURE_RISK",
            )

    def test_queue_record_has_memberships(self):
        row = command_queue_record(
            self._records()[0]
        )

        self.assertIn(
            QUEUE_URGENT_REVIEW,
            row["queues"],
        )

        self.assertIn(
            QUEUE_PENDING_APPROVAL,
            row["queues"],
        )

        self.assertIn(
            QUEUE_UNASSIGNED_CASES,
            row["queues"],
        )

    def test_queue_order_is_attention_first(self):
        rows = command_queue_rows(
            self._records(),
            QUEUE_HIGHEST_ATTENTION,
        )

        self.assertEqual(
            rows[0]["vehicleId"],
            "EV-001",
        )

        self.assertEqual(
            rows[1]["vehicleId"],
            "EV-002",
        )

    def test_queue_rank_is_materialized(self):
        rows = command_queue_rows(
            self._records(),
            QUEUE_HIGHEST_ATTENTION,
        )

        self.assertEqual(
            rows[0]["queueRank"],
            1,
        )

        self.assertEqual(
            rows[1]["queueRank"],
            2,
        )

    def test_queue_order_has_stable_vehicle_tiebreak(self):
        records = [
            {
                "vehicleId": "EV-B",
                "decisionState": "PLAN",
                "attentionScore": 50,
                "workloadUnits": 2,
                "topConfidence": 0.8,
            },
            {
                "vehicleId": "EV-A",
                "decisionState": "PLAN",
                "attentionScore": 50,
                "workloadUnits": 2,
                "topConfidence": 0.8,
            },
        ]

        rows = command_queue_rows(
            records,
            QUEUE_HIGHEST_ATTENTION,
        )

        self.assertEqual(
            [
                row["vehicleId"]
                for row in rows
            ],
            [
                "EV-A",
                "EV-B",
            ],
        )

    def test_queue_counts_cover_all_queues(self):
        result = queue_counts(
            self._records()
        )

        self.assertEqual(
            len(result),
            7,
        )

        self.assertEqual(
            {
                row["queue"]
                for row in result
            },
            set(FLEET_COMMAND_QUEUES),
        )

    def test_summary_population(self):
        result = command_center_summary(
            self._records()
        )

        self.assertEqual(
            result["totalVehicles"],
            3,
        )

        self.assertEqual(
            result["nonHealthyHypotheses"],
            2,
        )

        self.assertEqual(
            result["vehiclesWithCases"],
            2,
        )

    def test_summary_attention_count(self):
        result = command_center_summary(
            self._records()
        )

        self.assertEqual(
            result["attentionRequired"],
            2,
        )

    def test_summary_workload(self):
        result = command_center_summary(
            self._records()
        )

        self.assertEqual(
            result["totalWorkloadUnits"],
            5.5,
        )

    def test_summary_coverage_gaps(self):
        result = command_center_summary(
            self._records()
        )

        self.assertEqual(
            result[
                "vehiclesWithCoverageGaps"
            ],
            1,
        )

        self.assertEqual(
            result[
                "coverageGapInstances"
            ],
            3,
        )

    def test_summary_state_counts(self):
        result = command_center_summary(
            self._records()
        )

        by_state = {
            row["state"]: row["vehicles"]
            for row
            in result["byDecisionState"]
        }

        self.assertEqual(
            by_state["PLAN"],
            2,
        )

        self.assertEqual(
            by_state["NOMINAL"],
            1,
        )

    def test_full_vehicle_order(self):
        rows = command_vehicle_rows(
            self._records()
        )

        self.assertEqual(
            [
                row["vehicleId"]
                for row in rows
            ],
            [
                "EV-001",
                "EV-002",
                "EV-003",
            ],
        )

    def test_command_layer_rejects_physical_meaning(self):
        result = command_center_summary(
            self._records()
        )

        interpretation = result[
            "interpretation"
        ]

        self.assertFalse(
            interpretation[
                "queuePriorityIsPhysicalRisk"
            ]
        )

        self.assertFalse(
            interpretation[
                "physicalFailureProbability"
            ]
        )

        self.assertFalse(
            interpretation[
                "physicalConditionProof"
            ]
        )

        self.assertFalse(
            interpretation["physicalRul"]
        )

    def test_command_layer_rejects_causality_and_hours(self):
        result = command_center_summary(
            self._records()
        )

        interpretation = result[
            "interpretation"
        ]

        self.assertFalse(
            interpretation[
                "causalAttribution"
            ]
        )

        self.assertFalse(
            interpretation[
                "technicianHours"
            ]
        )


if __name__ == "__main__":
    unittest.main()
