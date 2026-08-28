import unittest
from datetime import datetime, timedelta, timezone

from fleetmind_common.asset_plugins import score_asset_event, validate_asset_event
from fleetmind_common.model_ops_rules import drift_report, promotion_readiness
from fleetmind_common.outcome_rules import (
    IMPROVED,
    WORSENED,
    evaluate_observed_outcome,
    outcome_evaluation_key,
)
from fleetmind_common.policy_evaluation_rules import (
    compare_shadow_results,
    evaluate_policy,
)


class RemainingPhaseRulesTests(unittest.TestCase):
    def test_outcome_key_is_stable(self):
        first = outcome_evaluation_key(recommendation_id=42)
        second = outcome_evaluation_key(recommendation_id=42)
        other = outcome_evaluation_key(recommendation_id=43)
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertEqual(len(first), 64)

    def test_observable_improvement(self):
        start = datetime(2026, 8, 27, tzinfo=timezone.utc)
        baseline = {
            "timestamp": start.isoformat(),
            "mileage": 1000.0,
            "riskScore": 0.82,
            "telemetryStatus": "critical",
            "topClass": "coolant_pump",
            "topConfidence": 0.91,
            "attentionScore": 84.0,
            "coverageGapCount": 3,
            "caseStatus": "INVESTIGATING",
        }
        post = {
            "timestamp": (start + timedelta(minutes=20)).isoformat(),
            "mileage": 1100.0,
            "riskScore": 0.20,
            "telemetryStatus": "healthy",
            "topClass": "healthy",
            "topConfidence": 0.82,
            "attentionScore": 22.0,
            "coverageGapCount": 0,
            "caseStatus": "MONITORING",
        }

        result = evaluate_observed_outcome(baseline, post)

        self.assertEqual(result["status"], IMPROVED)
        self.assertGreater(result["score"], 15.0)
        self.assertFalse(
            result["claimBoundary"]["maintenanceCausalityEstablished"]
        )

    def test_observable_worsening(self):
        start = datetime(2026, 8, 27, tzinfo=timezone.utc)
        baseline = {
            "timestamp": start.isoformat(),
            "mileage": 1000.0,
            "riskScore": 0.10,
            "telemetryStatus": "healthy",
            "topClass": "healthy",
            "topConfidence": 0.92,
            "attentionScore": 10.0,
            "coverageGapCount": 0,
            "caseStatus": "MONITORING",
        }
        post = {
            "timestamp": (start + timedelta(minutes=20)).isoformat(),
            "mileage": 1100.0,
            "riskScore": 0.88,
            "telemetryStatus": "critical",
            "topClass": "coolant_pump",
            "topConfidence": 0.90,
            "attentionScore": 90.0,
            "coverageGapCount": 3,
            "caseStatus": "ESCALATED",
        }

        result = evaluate_observed_outcome(baseline, post)

        self.assertEqual(result["status"], WORSENED)
        self.assertLess(result["score"], -15.0)

    def test_policy_replay_is_deduplicated_and_selective(self):
        candidates = [
            {
                "vehicleId": "EV-1",
                "caseId": 1,
                "recommendationType": "REVIEW_CASE",
                "priority": "P1",
                "sourceKey": "case:1:review",
                "context": {
                    "factory": "Austin",
                    "firmware": "2026.32.4",
                },
            },
            {
                "vehicleId": "EV-1",
                "caseId": 1,
                "recommendationType": "REVIEW_CASE",
                "priority": "P1",
                "sourceKey": "case:1:review",
                "context": {
                    "factory": "Austin",
                    "firmware": "2026.32.4",
                },
            },
            {
                "vehicleId": "EV-2",
                "caseId": 2,
                "recommendationType": "ASSIGN_CASE",
                "priority": "P3",
                "sourceKey": "case:2:assignment",
                "context": {
                    "factory": "Berlin",
                    "firmware": "2026.32.1",
                },
            },
        ]

        result = evaluate_policy(
            candidates,
            {
                "maximumPriorityRank": 2,
                "maximumCandidatesPerVehicle": 4,
            },
            input_is_frozen=True,
        )

        self.assertEqual(result["duplicateSuppressed"], 1)
        self.assertEqual(result["selectedCandidates"], 1)
        self.assertEqual(
            result["cohortCoverage"]["factory"]["Austin"],
            1,
        )
        self.assertTrue(result["promotionCriteria"]["met"])
        self.assertFalse(
            result["claimBoundary"]["productionBehaviorChanged"]
        )

    def test_policy_conflict_blocks_promotion(self):
        candidates = [
            {
                "vehicleId": "EV-1",
                "caseId": 1,
                "recommendationType": "REVIEW_CASE",
                "priority": "P1",
                "sourceKey": "a",
            },
            {
                "vehicleId": "EV-1",
                "caseId": 1,
                "recommendationType": "ASSIGN_CASE",
                "priority": "P1",
                "sourceKey": "b",
            },
        ]

        result = evaluate_policy(
            candidates,
            {
                "maximumPriorityRank": 3,
                "maximumCandidatesPerVehicle": 8,
                "conflictPairs": [
                    ["REVIEW_CASE", "ASSIGN_CASE"],
                ],
            },
            input_is_frozen=True,
        )

        self.assertEqual(len(result["conflicts"]), 1)
        self.assertFalse(result["promotionCriteria"]["met"])

    def test_shadow_comparison_is_no_write(self):
        control = evaluate_policy(
            [
                {
                    "vehicleId": "EV-1",
                    "recommendationType": "REVIEW_CASE",
                    "priority": "P1",
                    "sourceKey": "a",
                },
                {
                    "vehicleId": "EV-2",
                    "recommendationType": "ASSIGN_CASE",
                    "priority": "P3",
                    "sourceKey": "b",
                },
            ],
            {
                "maximumPriorityRank": 3,
                "maximumCandidatesPerVehicle": 8,
            },
            input_is_frozen=True,
        )
        candidate = evaluate_policy(
            [
                {
                    "vehicleId": "EV-1",
                    "recommendationType": "REVIEW_CASE",
                    "priority": "P1",
                    "sourceKey": "a",
                },
                {
                    "vehicleId": "EV-2",
                    "recommendationType": "ASSIGN_CASE",
                    "priority": "P3",
                    "sourceKey": "b",
                },
            ],
            {
                "maximumPriorityRank": 2,
                "maximumCandidatesPerVehicle": 8,
            },
            input_is_frozen=True,
        )

        comparison = compare_shadow_results(control, candidate)

        self.assertEqual(comparison["controlCandidateCount"], 2)
        self.assertEqual(comparison["candidateCandidateCount"], 1)
        self.assertEqual(comparison["candidateVolumeDelta"], -1)
        self.assertTrue(comparison["claimBoundary"]["shadowOnly"])
        self.assertFalse(
            comparison["claimBoundary"]["recommendationWrites"]
        )

    def test_model_promotion_gate(self):
        ready = promotion_readiness(
            artifact_sha256="a" * 64,
            feature_schema_sha256="b" * 64,
            active_feature_schema_sha256="b" * 64,
            benchmark_snapshot_sha256="c" * 64,
            benchmark_status="qualified",
        )
        blocked = promotion_readiness(
            artifact_sha256="a" * 64,
            feature_schema_sha256="b" * 64,
            active_feature_schema_sha256="d" * 64,
            benchmark_snapshot_sha256="c" * 64,
            benchmark_status="qualified",
        )

        self.assertTrue(ready["ready"])
        self.assertFalse(blocked["ready"])

    def test_drift_detection(self):
        report = drift_report(
            {
                "pump_current_a": {
                    "mean": 3.0,
                    "std": 0.2,
                    "count": 100,
                },
            },
            {
                "pump_current_a": {
                    "mean": 3.35,
                    "std": 0.2,
                    "count": 100,
                },
            },
        )

        self.assertEqual(report["status"], "DRIFT")
        self.assertGreater(
            report["features"][0]["standardizedMeanShift"],
            1.0,
        )

    def test_robot_asset_plugin(self):
        event = {
            "eventId": "asset-event-1",
            "timestamp": "2026-08-27T12:00:00+00:00",
            "experimentId": "asset-exp",
            "assetId": "RBT-00001",
            "assetType": "robot",
            "metrics": {
                "actuator_current_a": 25.0,
                "actuator_temp_c": 90.0,
                "actuator_torque_nm": 100.0,
                "gearbox_vibration_rms": 7.5,
                "gearbox_temp_c": 93.0,
            },
        }

        validation = validate_asset_event(event)
        score = score_asset_event(event)

        self.assertTrue(validation["valid"])
        self.assertEqual(score["status"], "critical")
        self.assertFalse(
            score["claimBoundary"]["autonomousControl"]
        )


if __name__ == "__main__":
    unittest.main()
