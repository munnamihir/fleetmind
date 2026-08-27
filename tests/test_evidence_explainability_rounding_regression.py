import unittest

from fleetmind_common.evidence_explainability_rules import (
    attention_score_decomposition,
)


class EvidenceExplainabilityRoundingRegressionTests(
    unittest.TestCase
):

    def test_rounding_delta_is_not_score_cap(self):
        # 0.333333 * 30 creates a non-integer weighted contribution.
        # Canonical Phase 7.0 scoring rounds to three decimals.
        # That rounding difference must not be represented as SCORE_CAP.
        record = {
            "topClass": "inverter",
            "topConfidence": 0.333333,
        }

        result = attention_score_decomposition(
            record
        )

        factors = [
            component["factor"]
            for component
            in result["components"]
        ]

        self.assertFalse(
            result["capApplied"]
        )

        self.assertEqual(
            result["capAdjustment"],
            0.0,
        )

        self.assertNotIn(
            "SCORE_CAP",
            factors,
        )

        self.assertTrue(
            result["reconciles"]
        )

        self.assertAlmostEqual(
            result["attentionScore"],
            result["explainedScore"],
            places=3,
        )


if __name__ == "__main__":
    unittest.main()
