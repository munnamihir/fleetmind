from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
RULES_PATH = (
    ROOT
    / "services/common/fleetmind_common/diagnostic_automation_rules.py"
)

spec = importlib.util.spec_from_file_location("automation_rules", RULES_PATH)
assert spec and spec.loader
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


class AutomationRulesTests(unittest.TestCase):
    def base_record(self):
        return {
            "maintenanceTier": "URGENT_REVIEW",
            "maintenancePlan": None,
            "episodeState": "EVOLVING",
            "watchlisted": False,
            "priorityScore": 78.0,
            "experimentalHorizon": {
                "thresholdAlreadyReached": True,
            },
        }

    def test_nested_value(self):
        record = self.base_record()
        self.assertTrue(
            rules.nested_value(
                record,
                "experimentalHorizon.thresholdAlreadyReached",
            )
        )
        self.assertIsNone(rules.nested_value(record, "missing.value"))

    def test_eq_condition(self):
        self.assertTrue(
            rules.condition_matches(
                self.base_record(),
                {"field": "maintenanceTier", "operator": "eq", "value": "URGENT_REVIEW"},
            )
        )

    def test_is_null_condition(self):
        self.assertTrue(
            rules.condition_matches(
                self.base_record(),
                {"field": "maintenancePlan", "operator": "is_null", "value": True},
            )
        )

    def test_gte_lte_conditions(self):
        record = self.base_record()
        self.assertTrue(
            rules.condition_matches(
                record,
                {"field": "priorityScore", "operator": "gte", "value": 70},
            )
        )
        self.assertTrue(
            rules.condition_matches(
                record,
                {"field": "priorityScore", "operator": "lte", "value": 80},
            )
        )

    def test_urgent_review_policy_matches_without_plan(self):
        policy = next(
            p
            for p in rules.DEFAULT_AUTOMATION_POLICIES
            if p["key"] == "urgent-review-without-plan"
        )
        self.assertTrue(rules.policy_matches(self.base_record(), policy))

    def test_urgent_review_policy_stops_matching_once_plan_exists(self):
        policy = next(
            p
            for p in rules.DEFAULT_AUTOMATION_POLICIES
            if p["key"] == "urgent-review-without-plan"
        )
        record = self.base_record()
        record["maintenancePlan"] = {"id": 1, "state": "REVIEW"}
        self.assertFalse(rules.policy_matches(record, policy))

    def test_destabilized_watchlist_policy(self):
        policy = next(
            p
            for p in rules.DEFAULT_AUTOMATION_POLICIES
            if p["key"] == "destabilized-not-watchlisted"
        )
        record = self.base_record()
        record["episodeState"] = "DESTABILIZED"
        self.assertTrue(rules.policy_matches(record, policy))
        record["watchlisted"] = True
        self.assertFalse(rules.policy_matches(record, policy))

    def test_policy_match_reason_is_deterministic(self):
        policy = next(
            p
            for p in rules.DEFAULT_AUTOMATION_POLICIES
            if p["key"] == "urgent-review-without-plan"
        )
        first = rules.policy_match_reason(self.base_record(), policy)
        second = rules.policy_match_reason(self.base_record(), policy)
        self.assertEqual(first, second)
        self.assertIn("maintenanceTier", first)
        self.assertIn("maintenancePlan", first)


if __name__ == "__main__":
    unittest.main()
