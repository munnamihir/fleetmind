import unittest

from fleetmind_common.evidence_explainability_rules import (
    ATTENTION_FACTOR_MODEL_CONFIDENCE,
    ATTENTION_FACTOR_SCORE_CAP,
    EVIDENCE_EXPLAINABILITY_RULES_VERSION,
    attention_score_decomposition,
    evidence_inventory,
    evidence_lineage,
    summarize_attention_explanations,
)
from fleetmind_common.fleet_decision_rules import (
    attention_score,
    coverage_gaps,
)


class EvidenceExplainabilityRulesMathTests(unittest.TestCase):

    def test_rules_version(self):
        result = attention_score_decomposition({})

        self.assertEqual(
            result["rulesVersion"],
            "fm-evidence-explainability-7.6-v1",
        )

        self.assertEqual(
            result["rulesVersion"],
            EVIDENCE_EXPLAINABILITY_RULES_VERSION,
        )

    def test_healthy_empty_record_scores_zero(self):
        result = attention_score_decomposition(
            {
                "topClass": "healthy",
                "topConfidence": 0.99,
            }
        )

        self.assertEqual(
            result["attentionScore"],
            0.0,
        )

        self.assertEqual(
            result["explainedScore"],
            0.0,
        )

        self.assertTrue(
            result["reconciles"]
        )

    def test_nonhealthy_confidence_matches_canonical_score(self):
        record = {
            "topClass": "battery_pack",
            "topConfidence": 0.8,
        }

        result = attention_score_decomposition(
            record
        )

        canonical = attention_score(
            record,
            coverage_gaps(record),
        )

        self.assertEqual(
            result["attentionScore"],
            canonical,
        )

        self.assertTrue(
            result["reconciles"]
        )

    def test_confidence_is_clamped_at_one(self):
        result = attention_score_decomposition(
            {
                "topClass": "battery_pack",
                "topConfidence": 9.0,
            }
        )

        confidence = next(
            component
            for component in result["components"]
            if component["factor"]
            == ATTENTION_FACTOR_MODEL_CONFIDENCE
        )

        self.assertEqual(
            confidence["contribution"],
            30.0,
        )

    def test_healthy_class_gets_no_confidence_points(self):
        result = attention_score_decomposition(
            {
                "topClass": "healthy",
                "topConfidence": 1.0,
            }
        )

        self.assertFalse(
            any(
                component["factor"]
                == ATTENTION_FACTOR_MODEL_CONFIDENCE
                for component
                in result["components"]
            )
        )

    def test_review_priority_weight(self):
        result = attention_score_decomposition(
            {
                "topClass": "healthy",
                "reviewPriority": "HIGH",
            }
        )

        self.assertEqual(
            result["attentionScore"],
            20.0,
        )

    def test_maintenance_tier_weight(self):
        result = attention_score_decomposition(
            {
                "topClass": "healthy",
                "maintenanceTier": "PLAN_SERVICE",
            }
        )

        self.assertEqual(
            result["attentionScore"],
            18.0,
        )

    def test_episode_state_weight(self):
        result = attention_score_decomposition(
            {
                "topClass": "healthy",
                "episodeState": "DESTABILIZED",
            }
        )

        self.assertEqual(
            result["attentionScore"],
            10.0,
        )

    def test_watchlist_weight(self):
        result = attention_score_decomposition(
            {
                "topClass": "healthy",
                "watchlisted": True,
            }
        )

        self.assertEqual(
            result["attentionScore"],
            2.0,
        )

    def test_multiple_factors_reconcile(self):
        record = {
            "topClass": "inverter",
            "topConfidence": 0.72,
            "reviewPriority": "MEDIUM",
            "maintenanceTier": "PLAN_SERVICE",
            "episodeState": "EVOLVING",
            "watchlisted": True,
        }

        result = attention_score_decomposition(
            record
        )

        canonical = attention_score(
            record,
            coverage_gaps(record),
        )

        self.assertEqual(
            result["attentionScore"],
            canonical,
        )

        self.assertEqual(
            result["explainedScore"],
            canonical,
        )

        self.assertTrue(
            result["reconciles"]
        )

    def test_coverage_gap_contributions_reconcile(self):
        record = {
            "topClass": "battery_pack",
            "topConfidence": 0.75,
            "caseId": None,
        }

        result = attention_score_decomposition(
            record
        )

        self.assertTrue(
            result["coverageGaps"]
        )

        self.assertEqual(
            result["attentionScore"],
            attention_score(
                record,
                coverage_gaps(record),
            ),
        )

        self.assertTrue(
            result["reconciles"]
        )

    def test_score_cap_is_explicit(self):
        record = {
            "topClass": "traction_motor",
            "topConfidence": 1.0,
            "reviewPriority": "HIGH",
            "maintenanceTier": "URGENT_REVIEW",
            "episodeState": "DESTABILIZED",
            "watchlisted": True,
            "caseId": 42,
            "assignedTo": None,
            "maintenancePlanState": None,
            "trajectoryEligible": False,
            "automationStatuses": [
                "PENDING_APPROVAL",
            ],
        }

        result = attention_score_decomposition(
            record
        )

        self.assertEqual(
            result["attentionScore"],
            100.0,
        )

        self.assertGreater(
            result["rawAttentionScore"],
            100.0,
        )

        self.assertTrue(
            result["capApplied"]
        )

        self.assertLess(
            result["capAdjustment"],
            0.0,
        )

        self.assertTrue(
            any(
                component["factor"]
                == ATTENTION_FACTOR_SCORE_CAP
                for component
                in result["components"]
            )
        )

        self.assertTrue(
            result["reconciles"]
        )

    def test_cap_reconciliation_equals_exact_score(self):
        record = {
            "topClass": "coolant_pump",
            "topConfidence": 0.987654,
            "reviewPriority": "HIGH",
            "maintenanceTier": "URGENT_REVIEW",
            "episodeState": "DESTABILIZED",
            "watchlisted": True,
            "caseId": 99,
            "assignedTo": None,
            "maintenancePlanState": None,
            "trajectoryEligible": False,
            "automationStatuses": [
                "PENDING_APPROVAL",
            ],
        }

        result = attention_score_decomposition(
            record
        )

        self.assertEqual(
            result["explainedScore"],
            result["attentionScore"],
        )

    def test_interpretation_rejects_shap(self):
        result = attention_score_decomposition({})

        interpretation = result["interpretation"]

        self.assertFalse(
            interpretation["shapValues"]
        )

        self.assertFalse(
            interpretation[
                "modelFeatureAttribution"
            ]
        )

        self.assertFalse(
            interpretation["causalAttribution"]
        )

    def test_interpretation_rejects_physical_risk(self):
        result = attention_score_decomposition({})

        interpretation = result["interpretation"]

        self.assertFalse(
            interpretation[
                "physicalFailureProbability"
            ]
        )

        self.assertFalse(
            interpretation[
                "physicalReliabilityProbability"
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

    def test_fleet_summary_reconciles_every_vehicle(self):
        records = [
            {
                "vehicleId": "EV-1",
                "topClass": "healthy",
            },
            {
                "vehicleId": "EV-2",
                "topClass": "battery_pack",
                "topConfidence": 0.8,
            },
            {
                "vehicleId": "EV-3",
                "topClass": "inverter",
                "topConfidence": 0.9,
                "reviewPriority": "HIGH",
                "maintenanceTier": "URGENT_REVIEW",
            },
        ]

        result = summarize_attention_explanations(
            records
        )

        self.assertEqual(
            result["vehicleCount"],
            3,
        )

        self.assertEqual(
            result["reconciledVehicleCount"],
            3,
        )

    def test_fleet_summary_is_deterministic(self):
        records = [
            {
                "topClass": "battery_pack",
                "topConfidence": 0.6,
            },
            {
                "topClass": "healthy",
                "reviewPriority": "MEDIUM",
            },
        ]

        first = summarize_attention_explanations(
            records
        )

        second = summarize_attention_explanations(
            records
        )

        self.assertEqual(
            first,
            second,
        )


if __name__ == "__main__":
    unittest.main()


class EvidenceLineageRulesMathTests(unittest.TestCase):

    def _twin(self):
        return {
            "vehicleId": "EV-TEST",
            "modelState": {
                "predictionId": 11,
                "topClass": "battery_pack",
                "topConfidence": 0.84,
                "anchorTimestamp": (
                    "2026-08-25T12:00:00+00:00"
                ),
                "anchorMileage": 12345.6,
                "observableEvidence": [
                    {"signal": "pack_voltage"},
                    {"signal": "pack_current"},
                ],
            },
            "diagnosticState": {
                "episodeId": 22,
                "episodeState": "EVOLVING",
                "hypothesisClass": "battery_pack",
                "isOpen": True,
            },
            "caseState": {
                "caseId": 33,
                "status": "ACKNOWLEDGED",
                "reviewPriority": "HIGH",
                "assignedTo": "operator-a",
                "watchlisted": True,
            },
            "prognosticState": {
                "maintenanceTier": "PLAN_SERVICE",
                "priorityScore": 71.0,
                "trajectoryEligible": True,
                "recommendedReviewWindow": (
                    "NEXT_REVIEW_WINDOW"
                ),
            },
            "maintenanceState": {
                "planId": 44,
                "state": "REVIEW",
                "owner": "operator-a",
                "targetMileage": 12500.0,
            },
            "automationState": {
                "actionIds": [55, 56],
                "currentStatus": "PENDING_APPROVAL",
                "pendingActionTypes": [
                    "ENSURE_REVIEW_PLAN",
                ],
                "actions": [
                    {"id": 55},
                    {"id": 56},
                ],
            },
            "fleetDecisionState": {
                "decisionState": "PLAN",
                "attentionScore": 82.2,
                "workloadUnits": 2.75,
            },
            "coverageState": {
                "coverageGaps": [
                    "PENDING_AUTOMATION_APPROVAL",
                ],
            },
            "sourceVersions": {
                "modelLineage": "test-lineage",
                "fleetDecisionRules": (
                    "fm-fleet-decision-7.0-v1"
                ),
            },
        }

    def test_inventory_counts_observable_evidence(self):
        result = evidence_inventory(
            self._twin()
        )

        self.assertEqual(
            result["observableModelEvidenceCount"],
            2,
        )

        self.assertEqual(
            result["automationActionCount"],
            2,
        )

        self.assertEqual(
            result["coverageGapCount"],
            1,
        )

    def test_inventory_reports_all_layers_present(self):
        result = evidence_inventory(
            self._twin()
        )

        self.assertEqual(
            result["totalLayerCount"],
            8,
        )

        self.assertEqual(
            result["presentLayerCount"],
            8,
        )

    def test_inventory_does_not_claim_physical_truth(self):
        result = evidence_inventory(
            self._twin()
        )

        interpretation = result["interpretation"]

        self.assertFalse(
            interpretation["usesPrivateFailureTruth"]
        )

        self.assertFalse(
            interpretation[
                "physicalConditionProof"
            ]
        )

        self.assertFalse(
            interpretation[
                "physicalFailureConfirmation"
            ]
        )

    def test_lineage_contains_expected_nodes(self):
        result = evidence_lineage(
            self._twin()
        )

        ids = {
            node["id"]
            for node in result["nodes"]
        }

        self.assertEqual(
            ids,
            {
                "model",
                "episode",
                "case",
                "prognostic",
                "maintenance",
                "automation",
                "fleet-decision",
                "coverage",
            },
        )

    def test_lineage_edges_are_explicitly_noncausal(self):
        result = evidence_lineage(
            self._twin()
        )

        self.assertTrue(
            result["edges"]
        )

        self.assertTrue(
            all(
                edge["causal"] is False
                for edge in result["edges"]
            )
        )

    def test_lineage_omits_absent_optional_layers(self):
        twin = self._twin()

        twin["maintenanceState"] = {
            "planId": None,
            "state": None,
        }

        twin["automationState"] = {
            "actionIds": [],
            "actions": [],
            "currentStatus": None,
        }

        result = evidence_lineage(twin)

        ids = {
            node["id"]
            for node in result["nodes"]
        }

        self.assertNotIn(
            "maintenance",
            ids,
        )

        self.assertNotIn(
            "automation",
            ids,
        )

        self.assertIn(
            "fleet-decision",
            ids,
        )

    def test_lineage_preserves_source_versions(self):
        result = evidence_lineage(
            self._twin()
        )

        self.assertEqual(
            result["sourceVersions"][
                "modelLineage"
            ],
            "test-lineage",
        )

    def test_lineage_is_not_causal_graph(self):
        result = evidence_lineage(
            self._twin()
        )

        interpretation = result["interpretation"]

        self.assertFalse(
            interpretation["causalGraph"]
        )

        self.assertFalse(
            interpretation[
                "causalAttribution"
            ]
        )

        self.assertFalse(
            interpretation[
                "physicalDependencyGraph"
            ]
        )


if __name__ == "__main__":
    unittest.main()
