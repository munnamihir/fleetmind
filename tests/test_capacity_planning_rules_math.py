from __future__ import annotations

import unittest

from fleetmind_common.capacity_planning_rules import (
    CAPACITY_PLANNING_RULES_VERSION,
    CAPACITY_PLANNING_STRATEGIES,
    eligible_capacity_records,
    simulate_capacity_plan,
)


class CapacityPlanningRulesMathTests(unittest.TestCase):

    def records(self):
        return [
            {
                "vehicleId": "A",
                "topClass": "inverter",
                "decisionState": "PLAN",
                "maintenanceTier": "URGENT_REVIEW",
                "attentionScore": 90.0,
                "workloadUnits": 2.5,
                "coverageGaps": ["G1", "G2"],
            },
            {
                "vehicleId": "B",
                "topClass": "coolant_pump",
                "decisionState": "PLAN",
                "maintenanceTier": "PLAN_SERVICE",
                "attentionScore": 70.0,
                "workloadUnits": 2.0,
                "coverageGaps": ["G1"],
            },
            {
                "vehicleId": "C",
                "topClass": "traction_motor",
                "decisionState": "OBSERVE",
                "maintenanceTier": "MONITOR",
                "attentionScore": 40.0,
                "workloadUnits": 0.5,
                "coverageGaps": [],
            },
            {
                "vehicleId": "D",
                "topClass": "healthy",
                "decisionState": "NOMINAL",
                "maintenanceTier": None,
                "attentionScore": 0.0,
                "workloadUnits": 0.0,
                "coverageGaps": [],
            },
        ]

    def test_version(self):
        self.assertEqual(
            CAPACITY_PLANNING_RULES_VERSION,
            "fm-capacity-planning-7.4-v1",
        )

    def test_five_strategies(self):
        self.assertEqual(
            len(CAPACITY_PLANNING_STRATEGIES),
            5,
        )

    def test_zero_workload_not_eligible(self):
        eligible = eligible_capacity_records(
            self.records()
        )

        self.assertEqual(
            {row["vehicleId"] for row in eligible},
            {"A", "B", "C"},
        )

    def test_capacity_never_exceeded(self):
        result = simulate_capacity_plan(
            self.records(),
            capacity_units=3.0,
            strategy="ATTENTION_FIRST",
        )

        self.assertLessEqual(
            result["allocatedCapacityUnits"],
            3.0,
        )

    def test_attention_first(self):
        result = simulate_capacity_plan(
            self.records(),
            capacity_units=2.5,
            strategy="ATTENTION_FIRST",
        )

        self.assertEqual(
            result["selection"][0]["vehicleId"],
            "A",
        )

    def test_urgent_first(self):
        result = simulate_capacity_plan(
            self.records(),
            capacity_units=2.5,
            strategy="URGENT_FIRST",
        )

        self.assertEqual(
            result["selection"][0]["vehicleId"],
            "A",
        )

    def test_coverage_gap_first(self):
        result = simulate_capacity_plan(
            self.records(),
            capacity_units=2.5,
            strategy="COVERAGE_GAP_FIRST",
        )

        self.assertEqual(
            result["selection"][0]["vehicleId"],
            "A",
        )

    def test_max_vehicle_constraint(self):
        result = simulate_capacity_plan(
            self.records(),
            capacity_units=10.0,
            strategy="BALANCED",
            max_vehicles=1,
        )

        self.assertEqual(
            result["selectedVehicles"],
            1,
        )

    def test_tier_filter(self):
        result = simulate_capacity_plan(
            self.records(),
            capacity_units=10.0,
            strategy="BALANCED",
            allowed_maintenance_tiers=[
                "PLAN_SERVICE",
            ],
        )

        self.assertEqual(
            result["eligibleVehicles"],
            1,
        )
        self.assertEqual(
            result["selection"][0]["vehicleId"],
            "B",
        )

    def test_decision_state_filter(self):
        result = simulate_capacity_plan(
            self.records(),
            capacity_units=10.0,
            strategy="BALANCED",
            allowed_decision_states=["OBSERVE"],
        )

        self.assertEqual(
            result["selectedVehicles"],
            1,
        )
        self.assertEqual(
            result["selection"][0]["vehicleId"],
            "C",
        )

    def test_gap_projection_is_simulated(self):
        result = simulate_capacity_plan(
            self.records(),
            capacity_units=2.5,
            strategy="ATTENTION_FIRST",
        )

        self.assertEqual(
            result[
                "simulatedAddressedCoverageGapInstances"
            ],
            2,
        )
        self.assertEqual(
            result[
                "simulatedRemainingCoverageGapInstances"
            ],
            1,
        )

    def test_negative_capacity_rejected(self):
        with self.assertRaises(ValueError):
            simulate_capacity_plan(
                self.records(),
                capacity_units=-1.0,
                strategy="BALANCED",
            )

    def test_invalid_strategy_rejected(self):
        with self.assertRaises(ValueError):
            simulate_capacity_plan(
                self.records(),
                capacity_units=5.0,
                strategy="PHYSICAL_FAILURE_RISK",
            )

    def test_interpretation_rejects_hours_claim(self):
        result = simulate_capacity_plan(
            self.records(),
            capacity_units=5.0,
            strategy="BALANCED",
        )

        text = result["interpretation"].lower()

        self.assertIn("not technician hours", text)
        self.assertIn("not evidence", text)


if __name__ == "__main__":
    unittest.main()
