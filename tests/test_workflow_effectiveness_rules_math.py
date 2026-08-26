from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from fleetmind_common.workflow_effectiveness_rules import (
    WORKFLOW_EFFECTIVENESS_RULES_VERSION,
    action_effectiveness,
    source_target_absent,
    summarize_policy_effectiveness,
    summarize_workflow_effectiveness,
)


class WorkflowEffectivenessRulesMathTests(
    unittest.TestCase
):

    def now(self):
        return datetime(
            2026,
            8,
            26,
            12,
            0,
            tzinfo=timezone.utc,
        )

    def review_action(self):
        start = self.now()

        return {
            "actionId": 1,
            "policyKey": "plan-service-without-plan",
            "vehicleId": "EV-1",
            "caseId": 10,
            "actionType": "ENSURE_REVIEW_PLAN",
            "status": "EXECUTED",
            "createdAt": start,
            "approvedAt": start + timedelta(hours=2),
            "rejectedAt": None,
            "executedAt": start + timedelta(hours=5),
            "sourceSnapshot": {
                "maintenancePlanPresent": False,
                "watchlisted": False,
            },
        }

    def test_version(self):
        self.assertEqual(
            WORKFLOW_EFFECTIVENESS_RULES_VERSION,
            "fm-workflow-effectiveness-7.5-v1",
        )

    def test_review_plan_source_target_absent(self):
        self.assertTrue(
            source_target_absent(
                self.review_action()
            )
        )

    def test_executed_review_plan_target_observed(self):
        result = action_effectiveness(
            self.review_action(),
            {
                "vehicleId": "EV-1",
                "maintenancePlanId": 99,
                "watchlisted": False,
            },
        )

        self.assertEqual(
            result["outcome"],
            "TARGET_OBSERVED",
        )

    def test_executed_target_not_observed(self):
        result = action_effectiveness(
            self.review_action(),
            {
                "vehicleId": "EV-1",
                "maintenancePlanId": None,
                "watchlisted": False,
            },
        )

        self.assertEqual(
            result["outcome"],
            "TARGET_NOT_OBSERVED",
        )

    def test_not_executed_not_counted_as_effect(self):
        action = self.review_action()
        action["status"] = "PENDING_APPROVAL"
        action["executedAt"] = None

        result = action_effectiveness(
            action,
            {
                "vehicleId": "EV-1",
                "maintenancePlanId": 99,
            },
        )

        self.assertEqual(
            result["outcome"],
            "NOT_EXECUTED",
        )

    def test_watchlist_target_observed(self):
        action = self.review_action()
        action["actionType"] = "ENSURE_WATCHLIST"

        result = action_effectiveness(
            action,
            {
                "vehicleId": "EV-1",
                "watchlisted": True,
            },
        )

        self.assertEqual(
            result["outcome"],
            "TARGET_OBSERVED",
        )

    def test_hours_to_approval_and_execution(self):
        result = action_effectiveness(
            self.review_action(),
            {
                "vehicleId": "EV-1",
                "maintenancePlanId": 99,
            },
        )

        self.assertEqual(
            result["hoursToApproval"],
            2.0,
        )
        self.assertEqual(
            result["hoursToExecution"],
            5.0,
        )

    def test_policy_rates(self):
        action = self.review_action()

        summary = summarize_policy_effectiveness(
            policy_key="p1",
            actions=[action],
            current_by_vehicle={
                "EV-1": {
                    "maintenancePlanId": 99,
                }
            },
            current_match_count=3,
        )

        self.assertEqual(
            summary["currentMatches"],
            3,
        )
        self.assertEqual(
            summary["approvalRatePct"],
            100.0,
        )
        self.assertEqual(
            summary["executionRatePct"],
            100.0,
        )
        self.assertEqual(
            summary[
                "executedTargetObservationRatePct"
            ],
            100.0,
        )

    def test_rejection_rate(self):
        action = self.review_action()
        action["status"] = "REJECTED"
        action["approvedAt"] = None
        action["executedAt"] = None
        action["rejectedAt"] = (
            self.now() + timedelta(hours=1)
        )

        summary = summarize_policy_effectiveness(
            policy_key="p1",
            actions=[action],
            current_by_vehicle={},
        )

        self.assertEqual(
            summary["rejectionRatePct"],
            100.0,
        )

    def test_median_lifecycle_time(self):
        first = self.review_action()

        second = dict(self.review_action())
        second["actionId"] = 2
        second["approvedAt"] = (
            self.now() + timedelta(hours=4)
        )
        second["executedAt"] = (
            self.now() + timedelta(hours=7)
        )

        summary = summarize_policy_effectiveness(
            policy_key="p1",
            actions=[first, second],
            current_by_vehicle={
                "EV-1": {
                    "maintenancePlanId": 99,
                }
            },
        )

        self.assertEqual(
            summary["medianHoursToApproval"],
            3.0,
        )
        self.assertEqual(
            summary["medianHoursToExecution"],
            6.0,
        )

    def test_aggregate_summary(self):
        policy = {
            "currentMatches": 5,
            "materializedActions": 4,
            "pendingApproval": 1,
            "approvedReady": 1,
            "rejected": 1,
            "executed": 1,
            "everApproved": 2,
            "evaluableExecutedActions": 1,
            "executedTargetObserved": 1,
        }

        result = summarize_workflow_effectiveness(
            [policy]
        )

        self.assertEqual(
            result["totalActions"],
            4,
        )
        self.assertEqual(
            result["executionRatePct"],
            25.0,
        )
        self.assertEqual(
            result[
                "executedTargetObservationRatePct"
            ],
            100.0,
        )

    def test_interpretation_is_non_causal(self):
        result = action_effectiveness(
            self.review_action(),
            {
                "maintenancePlanId": 99,
            },
        )

        text = result["interpretation"].lower()

        self.assertIn("does not prove", text)
        self.assertIn("caused", text)
        self.assertIn("physical", text)


if __name__ == "__main__":
    unittest.main()
