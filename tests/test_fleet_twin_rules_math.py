from __future__ import annotations

import unittest

from fleetmind_common.fleet_twin_rules import (
    FLEET_TWIN_RULES_VERSION,
    cohort_exposure_rows,
    compare_cohort_exposure,
    fleet_exposure_summary,
)


class FleetTwinRulesMathTests(unittest.TestCase):
    def records(self):
        return [
            {
                "vehicleId": "A",
                "factory": "Austin",
                "model": "CT",
                "firmware": "1",
                "pumpRevision": "P1",
                "topClass": "healthy",
                "decisionState": "NOMINAL",
                "caseId": None,
                "coverageGaps": [],
                "attentionScore": 0.0,
                "workloadUnits": 0.0,
            },
            {
                "vehicleId": "B",
                "factory": "Austin",
                "model": "CT",
                "firmware": "1",
                "pumpRevision": "P1",
                "topClass": "inverter",
                "decisionState": "PLAN",
                "caseId": 1,
                "coverageGaps": ["UNASSIGNED_CASE"],
                "attentionScore": 60.0,
                "workloadUnits": 2.5,
            },
            {
                "vehicleId": "C",
                "factory": "Berlin",
                "model": "S3",
                "firmware": "2",
                "pumpRevision": "P2",
                "topClass": "inverter",
                "decisionState": "OBSERVE",
                "caseId": None,
                "coverageGaps": ["NONHEALTHY_WITHOUT_CASE"],
                "attentionScore": 30.0,
                "workloadUnits": 0.5,
            },
            {
                "vehicleId": "D",
                "factory": "Berlin",
                "model": "S3",
                "firmware": "2",
                "pumpRevision": "P2",
                "topClass": "coolant_pump",
                "decisionState": "PLAN",
                "caseId": 2,
                "coverageGaps": [
                    "UNASSIGNED_CASE",
                    "PRIORITY_CASE_WITHOUT_PLAN",
                ],
                "attentionScore": 70.0,
                "workloadUnits": 3.0,
            },
        ]

    def test_version(self):
        self.assertEqual(
            FLEET_TWIN_RULES_VERSION,
            "fm-fleet-twin-7.2-v1",
        )

    def test_fleet_summary_count_vs_rate(self):
        summary = fleet_exposure_summary(self.records())

        self.assertEqual(summary["populationCount"], 4)
        self.assertEqual(summary["nonHealthyCount"], 3)
        self.assertEqual(summary["nonHealthyRatePct"], 75.0)
        self.assertEqual(summary["coverageGapVehicleCount"], 3)
        self.assertEqual(summary["coverageGapInstances"], 4)

    def test_workload_normalized_per_100(self):
        summary = fleet_exposure_summary(self.records())

        self.assertEqual(summary["totalWorkloadUnits"], 6.0)
        self.assertEqual(summary["workloadUnitsPer100Vehicles"], 150.0)

    def test_factory_population_denominator(self):
        rows = cohort_exposure_rows(self.records(), "factory")
        by_value = {row["value"]: row for row in rows}

        self.assertEqual(by_value["Austin"]["populationCount"], 2)
        self.assertEqual(by_value["Berlin"]["populationCount"], 2)

        self.assertEqual(by_value["Austin"]["nonHealthyCount"], 1)
        self.assertEqual(by_value["Austin"]["nonHealthyRatePct"], 50.0)

        self.assertEqual(by_value["Berlin"]["nonHealthyCount"], 2)
        self.assertEqual(by_value["Berlin"]["nonHealthyRatePct"], 100.0)

    def test_rate_to_fleet_is_not_raw_count(self):
        rows = cohort_exposure_rows(self.records(), "factory")
        by_value = {row["value"]: row for row in rows}

        self.assertEqual(
            by_value["Austin"]["rateToFleetRatio"]["nonHealthy"],
            0.667,
        )
        self.assertEqual(
            by_value["Berlin"]["rateToFleetRatio"]["nonHealthy"],
            1.333,
        )

    def test_population_share(self):
        rows = cohort_exposure_rows(self.records(), "factory")
        by_value = {row["value"]: row for row in rows}

        self.assertEqual(by_value["Austin"]["populationSharePct"], 50.0)
        self.assertEqual(by_value["Berlin"]["populationSharePct"], 50.0)

    def test_hypothesis_dimension_uses_top_class(self):
        rows = cohort_exposure_rows(
            self.records(),
            "hypothesisClass",
        )
        values = {row["value"] for row in rows}

        self.assertEqual(
            values,
            {"healthy", "inverter", "coolant_pump"},
        )

    def test_empty_population_safe(self):
        summary = fleet_exposure_summary([])

        self.assertEqual(summary["populationCount"], 0)
        self.assertEqual(summary["attentionRatePct"], 0.0)
        self.assertEqual(summary["workloadUnitsPer100Vehicles"], 0.0)

    def test_compare_uses_rates(self):
        rows = cohort_exposure_rows(self.records(), "factory")
        by_value = {row["value"]: row for row in rows}

        result = compare_cohort_exposure(
            by_value["Austin"],
            by_value["Berlin"],
            measure="nonHealthy",
        )

        self.assertEqual(result["referenceRatePct"], 50.0)
        self.assertEqual(result["candidateRatePct"], 100.0)
        self.assertEqual(result["rateDeltaPctPoints"], 50.0)
        self.assertEqual(
            result["candidateToReferenceRateRatio"],
            2.0,
        )

    def test_invalid_dimension_rejected(self):
        with self.assertRaises(ValueError):
            cohort_exposure_rows(self.records(), "physicalFailureRisk")


if __name__ == "__main__":
    unittest.main()
