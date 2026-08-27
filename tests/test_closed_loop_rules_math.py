import unittest

from fleetmind_common.closed_loop_rules import (
    CLOSED_LOOP_RECOMMENDATION_TYPES,
    CLOSED_LOOP_RULES_VERSION,
    CLOSED_LOOP_STATES,
    PRIORITY_P0,
    PRIORITY_P1,
    PRIORITY_P2,
    PRIORITY_P3,
    RECOMMENDATION_ADD_WATCHLIST,
    RECOMMENDATION_ASSIGN_CASE,
    RECOMMENDATION_CREATE_REVIEW_PLAN,
    RECOMMENDATION_REVIEW_AUTOMATION_ACTION,
    RECOMMENDATION_REVIEW_CASE,
    STATE_ACKNOWLEDGED,
    STATE_APPROVAL_REQUIRED,
    STATE_APPROVED,
    STATE_CANCELLED,
    STATE_EXECUTED,
    STATE_EXECUTION_READY,
    STATE_PROPOSED,
    STATE_REJECTED,
    STATE_SUPERSEDED,
    allowed_next_states,
    approval_required_before_execution,
    can_transition,
    is_terminal_state,
    recommendation_candidates,
    recommendation_key,
    recommendation_priority,
    require_transition,
    summarize_recommendation_candidates,
)


class ClosedLoopRulesMathTests(
    unittest.TestCase
):

    def _record(self):
        return {
            "vehicleId": "EV-000001",
            "caseId": 101,
            "reviewPriority": "HIGH",
            "maintenanceTier": (
                "URGENT_REVIEW"
            ),
            "episodeState": (
                "DESTABILIZED"
            ),
            "decisionState": "PLAN",
            "attentionScore": 91.0,
            "assignedTo": None,
            "coverageGaps": [
                "UNASSIGNED_CASE",
                "PRIORITY_CASE_WITHOUT_PLAN",
                "DESTABILIZED_NOT_WATCHLISTED",
                "PENDING_AUTOMATION_APPROVAL",
            ],
            "automationStatuses": [
                "PENDING_APPROVAL",
            ],
            "automationStatus": (
                "PENDING_APPROVAL"
            ),
        }

    def test_rules_version(self):
        self.assertEqual(
            CLOSED_LOOP_RULES_VERSION,
            (
                "fm-closed-loop-"
                "operations-8.0-v1"
            ),
        )

    def test_nine_lifecycle_states(self):
        self.assertEqual(
            len(CLOSED_LOOP_STATES),
            9,
        )

    def test_five_recommendation_types(self):
        self.assertEqual(
            len(
                CLOSED_LOOP_RECOMMENDATION_TYPES
            ),
            5,
        )

    def test_proposed_can_acknowledge(self):
        self.assertTrue(
            can_transition(
                STATE_PROPOSED,
                STATE_ACKNOWLEDGED,
            )
        )

    def test_acknowledged_can_request_approval(self):
        self.assertTrue(
            can_transition(
                STATE_ACKNOWLEDGED,
                STATE_APPROVAL_REQUIRED,
            )
        )

    def test_approval_required_can_approve(self):
        self.assertTrue(
            can_transition(
                STATE_APPROVAL_REQUIRED,
                STATE_APPROVED,
            )
        )

    def test_approved_can_become_execution_ready(self):
        self.assertTrue(
            can_transition(
                STATE_APPROVED,
                STATE_EXECUTION_READY,
            )
        )

    def test_execution_ready_can_execute(self):
        self.assertTrue(
            can_transition(
                STATE_EXECUTION_READY,
                STATE_EXECUTED,
            )
        )

    def test_proposed_cannot_execute(self):
        self.assertFalse(
            can_transition(
                STATE_PROPOSED,
                STATE_EXECUTED,
            )
        )

    def test_acknowledged_cannot_execute(self):
        self.assertFalse(
            can_transition(
                STATE_ACKNOWLEDGED,
                STATE_EXECUTED,
            )
        )

    def test_approval_required_cannot_execute(self):
        self.assertFalse(
            can_transition(
                STATE_APPROVAL_REQUIRED,
                STATE_EXECUTED,
            )
        )

    def test_approved_cannot_skip_execution_ready(self):
        self.assertFalse(
            can_transition(
                STATE_APPROVED,
                STATE_EXECUTED,
            )
        )

    def test_require_transition_rejects_skip(self):
        with self.assertRaises(
            ValueError
        ):
            require_transition(
                STATE_PROPOSED,
                STATE_APPROVED,
            )

    def test_terminal_states_have_no_next_states(self):
        for state in (
            STATE_EXECUTED,
            STATE_REJECTED,
            STATE_CANCELLED,
            STATE_SUPERSEDED,
        ):
            self.assertTrue(
                is_terminal_state(
                    state
                )
            )

            self.assertEqual(
                allowed_next_states(
                    state
                ),
                (),
            )

    def test_rejected_is_terminal(self):
        self.assertTrue(
            is_terminal_state(
                STATE_REJECTED
            )
        )

    def test_approval_is_always_required(self):
        self.assertTrue(
            approval_required_before_execution()
        )

    def test_recommendation_key_is_deterministic(self):
        kwargs = {
            "run_id": 5,
            "experiment_id": "exp-test",
            "vehicle_id": "EV-1",
            "recommendation_type": (
                RECOMMENDATION_REVIEW_CASE
            ),
            "case_id": 10,
            "source_key": "case:10:review",
        }

        first = recommendation_key(
            **kwargs
        )

        second = recommendation_key(
            **kwargs
        )

        self.assertEqual(
            first,
            second,
        )

    def test_recommendation_key_changes_with_target(self):
        first = recommendation_key(
            run_id=5,
            experiment_id="exp-test",
            vehicle_id="EV-1",
            recommendation_type=(
                RECOMMENDATION_REVIEW_CASE
            ),
            case_id=10,
            source_key="case:10:review",
        )

        second = recommendation_key(
            run_id=5,
            experiment_id="exp-test",
            vehicle_id="EV-2",
            recommendation_type=(
                RECOMMENDATION_REVIEW_CASE
            ),
            case_id=10,
            source_key="case:10:review",
        )

        self.assertNotEqual(
            first,
            second,
        )

    def test_priority_p0(self):
        self.assertEqual(
            recommendation_priority(
                self._record(),
                RECOMMENDATION_REVIEW_CASE,
            ),
            PRIORITY_P0,
        )

    def test_priority_p1(self):
        record = {
            "maintenanceTier": (
                "PLAN_SERVICE"
            ),
            "attentionScore": 50,
        }

        self.assertEqual(
            recommendation_priority(
                record,
                RECOMMENDATION_REVIEW_CASE,
            ),
            PRIORITY_P1,
        )

    def test_priority_p2(self):
        record = {
            "reviewPriority": "MEDIUM",
            "attentionScore": 45,
        }

        self.assertEqual(
            recommendation_priority(
                record,
                RECOMMENDATION_REVIEW_CASE,
            ),
            PRIORITY_P2,
        )

    def test_priority_p3(self):
        record = {
            "attentionScore": 10,
        }

        self.assertEqual(
            recommendation_priority(
                record,
                RECOMMENDATION_REVIEW_CASE,
            ),
            PRIORITY_P3,
        )

    def test_record_generates_review_case(self):
        types = {
            row[
                "recommendationType"
            ]
            for row
            in recommendation_candidates(
                self._record()
            )
        }

        self.assertIn(
            RECOMMENDATION_REVIEW_CASE,
            types,
        )

    def test_record_generates_assignment(self):
        types = {
            row[
                "recommendationType"
            ]
            for row
            in recommendation_candidates(
                self._record()
            )
        }

        self.assertIn(
            RECOMMENDATION_ASSIGN_CASE,
            types,
        )

    def test_record_generates_review_plan(self):
        types = {
            row[
                "recommendationType"
            ]
            for row
            in recommendation_candidates(
                self._record()
            )
        }

        self.assertIn(
            RECOMMENDATION_CREATE_REVIEW_PLAN,
            types,
        )

    def test_record_generates_watchlist(self):
        types = {
            row[
                "recommendationType"
            ]
            for row
            in recommendation_candidates(
                self._record()
            )
        }

        self.assertIn(
            RECOMMENDATION_ADD_WATCHLIST,
            types,
        )

    def test_record_generates_automation_review(self):
        types = {
            row[
                "recommendationType"
            ]
            for row
            in recommendation_candidates(
                self._record()
            )
        }

        self.assertIn(
            (
                RECOMMENDATION_REVIEW_AUTOMATION_ACTION
            ),
            types,
        )

    def test_candidate_is_never_automatic_execution(self):
        candidates = (
            recommendation_candidates(
                self._record()
            )
        )

        self.assertTrue(
            all(
                row[
                    "automaticExecution"
                ]
                is False
                for row in candidates
            )
        )

    def test_candidate_is_not_physical_action(self):
        candidates = (
            recommendation_candidates(
                self._record()
            )
        )

        self.assertTrue(
            all(
                row["physicalAction"]
                is False
                for row in candidates
            )
        )

    def test_candidate_initial_state_is_proposed(self):
        candidates = (
            recommendation_candidates(
                self._record()
            )
        )

        self.assertTrue(
            all(
                row["initialState"]
                == STATE_PROPOSED
                for row in candidates
            )
        )

    def test_summary_is_no_write(self):
        result = (
            summarize_recommendation_candidates(
                [self._record()]
            )
        )

        self.assertFalse(
            result["interpretation"][
                "evaluationWrites"
            ]
        )

        self.assertFalse(
            result["interpretation"][
                "automaticApproval"
            ]
        )

        self.assertFalse(
            result["interpretation"][
                "automaticExecution"
            ]
        )

    def test_summary_rejects_physical_meaning(self):
        result = (
            summarize_recommendation_candidates(
                [self._record()]
            )
        )

        interpretation = result[
            "interpretation"
        ]

        self.assertFalse(
            interpretation[
                "physicalAction"
            ]
        )

        self.assertFalse(
            interpretation[
                "physicalFailureTruth"
            ]
        )

        self.assertFalse(
            interpretation[
                "physicalSafetyDecision"
            ]
        )

        self.assertFalse(
            interpretation[
                "causalAttribution"
            ]
        )


if __name__ == "__main__":
    unittest.main()
