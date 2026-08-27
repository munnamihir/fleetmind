import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from fleetmind_common.decision_queue_rules import (
    AGE_AGING,
    AGE_NEW,
    AGE_OVERDUE,
    AGE_STALE,
    DECISION_QUEUE_AGE_BUCKETS,
    DECISION_QUEUE_RULES_VERSION,
    active_queue_status,
    age_bucket,
    assignment_allowed,
    decision_queue_record,
    decision_queue_rows,
    decision_queue_summary,
    queue_age_hours,
    review_target_hours,
    review_target_overdue,
)

from fleetmind_common.closed_loop_rules import (
    STATE_ACKNOWLEDGED,
    STATE_APPROVAL_REQUIRED,
    STATE_APPROVED,
    STATE_CANCELLED,
    STATE_EXECUTED,
    STATE_EXECUTION_READY,
    STATE_PROPOSED,
    STATE_REJECTED,
    STATE_SUPERSEDED,
)


class DecisionQueueRulesMathTests(
    unittest.TestCase
):

    def setUp(self):
        self.now = datetime(
            2026,
            8,
            27,
            12,
            0,
            tzinfo=timezone.utc,
        )

    def _rec(
        self,
        *,
        recommendation_id=1,
        priority="P1",
        status=STATE_PROPOSED,
        age=10,
        assigned_to=None,
    ):
        return {
            "id": recommendation_id,
            "runId": 5,
            "experimentId": "exp-test",
            "vehicleId": (
                f"EV-{recommendation_id:03d}"
            ),
            "caseId": recommendation_id,
            "recommendationType": (
                "REVIEW_CASE"
            ),
            "priority": priority,
            "status": status,
            "approvalRequired": True,
            "assignedTo": assigned_to,
            "assignedAt": (
                self.now
                - timedelta(
                    hours=age - 1
                )
                if assigned_to
                else None
            ),
            "createdAt": (
                self.now
                - timedelta(
                    hours=age
                )
            ),
            "updatedAt": (
                self.now
                - timedelta(
                    hours=1
                )
            ),
        }

    def test_rules_version(self):
        self.assertEqual(
            DECISION_QUEUE_RULES_VERSION,
            "fm-decision-queue-8.1-v1",
        )

    def test_four_age_buckets(self):
        self.assertEqual(
            len(
                DECISION_QUEUE_AGE_BUCKETS
            ),
            4,
        )

    def test_age_new(self):
        self.assertEqual(
            age_bucket(3.99),
            AGE_NEW,
        )

    def test_age_aging(self):
        self.assertEqual(
            age_bucket(4),
            AGE_AGING,
        )

        self.assertEqual(
            age_bucket(23.99),
            AGE_AGING,
        )

    def test_age_overdue(self):
        self.assertEqual(
            age_bucket(24),
            AGE_OVERDUE,
        )

        self.assertEqual(
            age_bucket(71.99),
            AGE_OVERDUE,
        )

    def test_age_stale(self):
        self.assertEqual(
            age_bucket(72),
            AGE_STALE,
        )

    def test_negative_age_is_clamped(self):
        created = (
            self.now
            + timedelta(hours=4)
        )

        self.assertEqual(
            queue_age_hours(
                created,
                self.now,
            ),
            0.0,
        )

    def test_p0_target(self):
        self.assertEqual(
            review_target_hours("P0"),
            4.0,
        )

    def test_p1_target(self):
        self.assertEqual(
            review_target_hours("P1"),
            12.0,
        )

    def test_p2_target(self):
        self.assertEqual(
            review_target_hours("P2"),
            24.0,
        )

    def test_p3_target(self):
        self.assertEqual(
            review_target_hours("P3"),
            72.0,
        )

    def test_target_overdue_at_boundary(self):
        self.assertTrue(
            review_target_overdue(
                "P1",
                12,
            )
        )

    def test_target_not_overdue_before_boundary(self):
        self.assertFalse(
            review_target_overdue(
                "P1",
                11.999,
            )
        )

    def test_proposed_is_active(self):
        self.assertTrue(
            active_queue_status(
                STATE_PROPOSED
            )
        )

    def test_approval_states_are_active(self):
        for state in (
            STATE_ACKNOWLEDGED,
            STATE_APPROVAL_REQUIRED,
            STATE_APPROVED,
            STATE_EXECUTION_READY,
        ):
            self.assertTrue(
                active_queue_status(
                    state
                )
            )

    def test_terminal_states_inactive(self):
        for state in (
            STATE_EXECUTED,
            STATE_REJECTED,
            STATE_CANCELLED,
            STATE_SUPERSEDED,
        ):
            self.assertFalse(
                active_queue_status(
                    state
                )
            )

    def test_assignment_allowed_active(self):
        self.assertTrue(
            assignment_allowed(
                STATE_PROPOSED
            )
        )

    def test_assignment_blocked_terminal(self):
        self.assertFalse(
            assignment_allowed(
                STATE_EXECUTED
            )
        )

    def test_queue_record_age(self):
        row = decision_queue_record(
            self._rec(
                age=10
            ),
            now=self.now,
        )

        self.assertEqual(
            row["ageHours"],
            10.0,
        )

        self.assertEqual(
            row["ageBucket"],
            AGE_AGING,
        )

    def test_queue_record_unassigned(self):
        row = decision_queue_record(
            self._rec(),
            now=self.now,
        )

        self.assertTrue(
            row["unassigned"]
        )

    def test_queue_record_assigned(self):
        row = decision_queue_record(
            self._rec(
                assigned_to="operator-a"
            ),
            now=self.now,
        )

        self.assertFalse(
            row["unassigned"]
        )

        self.assertEqual(
            row["assignedTo"],
            "operator-a",
        )

    def test_queue_priority_orders_p0_first(self):
        rows = decision_queue_rows(
            [
                self._rec(
                    recommendation_id=1,
                    priority="P2",
                ),
                self._rec(
                    recommendation_id=2,
                    priority="P0",
                ),
                self._rec(
                    recommendation_id=3,
                    priority="P1",
                ),
            ],
            now=self.now,
        )

        self.assertEqual(
            [
                row["priority"]
                for row in rows
            ],
            [
                "P0",
                "P1",
                "P2",
            ],
        )

    def test_same_priority_overdue_first(self):
        rows = decision_queue_rows(
            [
                self._rec(
                    recommendation_id=1,
                    priority="P1",
                    age=5,
                ),
                self._rec(
                    recommendation_id=2,
                    priority="P1",
                    age=20,
                ),
            ],
            now=self.now,
        )

        self.assertEqual(
            rows[0]["id"],
            2,
        )

    def test_same_priority_unassigned_before_assigned(self):
        rows = decision_queue_rows(
            [
                self._rec(
                    recommendation_id=1,
                    priority="P1",
                    age=10,
                    assigned_to="operator",
                ),
                self._rec(
                    recommendation_id=2,
                    priority="P1",
                    age=10,
                ),
            ],
            now=self.now,
        )

        self.assertEqual(
            rows[0]["id"],
            2,
        )

    def test_same_priority_age_then_id(self):
        rows = decision_queue_rows(
            [
                self._rec(
                    recommendation_id=3,
                    age=8,
                ),
                self._rec(
                    recommendation_id=2,
                    age=10,
                ),
                self._rec(
                    recommendation_id=1,
                    age=10,
                ),
            ],
            now=self.now,
        )

        self.assertEqual(
            [
                row["id"]
                for row in rows
            ],
            [
                1,
                2,
                3,
            ],
        )

    def test_terminal_excluded_by_default(self):
        rows = decision_queue_rows(
            [
                self._rec(
                    recommendation_id=1,
                    status=STATE_PROPOSED,
                ),
                self._rec(
                    recommendation_id=2,
                    status=STATE_EXECUTED,
                ),
            ],
            now=self.now,
        )

        self.assertEqual(
            len(rows),
            1,
        )

    def test_terminal_can_be_included(self):
        rows = decision_queue_rows(
            [
                self._rec(
                    recommendation_id=1,
                    status=STATE_PROPOSED,
                ),
                self._rec(
                    recommendation_id=2,
                    status=STATE_EXECUTED,
                ),
            ],
            now=self.now,
            include_terminal=True,
        )

        self.assertEqual(
            len(rows),
            2,
        )

    def test_queue_rank_materialized(self):
        rows = decision_queue_rows(
            [
                self._rec(
                    recommendation_id=2,
                ),
                self._rec(
                    recommendation_id=1,
                ),
            ],
            now=self.now,
        )

        self.assertEqual(
            rows[0]["queueRank"],
            1,
        )

        self.assertEqual(
            rows[1]["queueRank"],
            2,
        )

    def test_summary_counts_active_and_terminal(self):
        result = decision_queue_summary(
            [
                self._rec(
                    recommendation_id=1,
                    status=STATE_PROPOSED,
                ),
                self._rec(
                    recommendation_id=2,
                    status=STATE_EXECUTED,
                ),
            ],
            now=self.now,
        )

        self.assertEqual(
            result[
                "activeRecommendations"
            ],
            1,
        )

        self.assertEqual(
            result[
                "terminalRecommendations"
            ],
            1,
        )

    def test_summary_counts_unassigned(self):
        result = decision_queue_summary(
            [
                self._rec(
                    recommendation_id=1,
                ),
                self._rec(
                    recommendation_id=2,
                    assigned_to="operator",
                ),
            ],
            now=self.now,
        )

        self.assertEqual(
            result[
                "unassignedActive"
            ],
            1,
        )

    def test_summary_rejects_physical_semantics(self):
        result = decision_queue_summary(
            [
                self._rec()
            ],
            now=self.now,
        )

        interpretation = result[
            "interpretation"
        ]

        self.assertFalse(
            interpretation[
                "ageIsPhysicalCondition"
            ]
        )

        self.assertFalse(
            interpretation[
                "priorityIsPhysicalRisk"
            ]
        )

        self.assertFalse(
            interpretation[
                "reviewTargetIsSafetyDeadline"
            ]
        )

        self.assertFalse(
            interpretation[
                "technicianHours"
            ]
        )

        self.assertFalse(
            interpretation[
                "causalAttribution"
            ]
        )


if __name__ == "__main__":
    unittest.main()
