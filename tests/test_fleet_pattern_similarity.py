from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
RULES = (
    ROOT
    / "services/common/fleetmind_common/diagnostic_pattern_rules.py"
)

spec = importlib.util.spec_from_file_location(
    "diagnostic_pattern_rules",
    RULES,
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class FleetPatternSimilarityTests(unittest.TestCase):
    def test_identical_records_score_one(self):
        record = {
            "hypothesisClass": "inverter",
            "reviewPriority": "HIGH",
            "episodeState": "EVOLVING",
            "firmware": "2026.8.1",
            "factory": "F1",
            "pumpRevision": "P2",
            "model": "S",
        }
        score, matched = module.similarity_score(record, dict(record))
        self.assertAlmostEqual(score, 1.0)
        self.assertEqual(len(matched), 7)

    def test_unrelated_records_score_zero(self):
        left = {
            "hypothesisClass": "inverter",
            "reviewPriority": "HIGH",
            "episodeState": "EVOLVING",
            "firmware": "A",
            "factory": "F1",
            "pumpRevision": "P1",
            "model": "S",
        }
        right = {
            "hypothesisClass": "battery_pack",
            "reviewPriority": "LOW",
            "episodeState": "STABILIZED",
            "firmware": "B",
            "factory": "F2",
            "pumpRevision": "P2",
            "model": "X",
        }
        score, matched = module.similarity_score(left, right)
        self.assertEqual(score, 0.0)
        self.assertEqual(matched, [])

    def test_same_hypothesis_has_largest_single_weight(self):
        left = {
            "hypothesisClass": "inverter",
            "reviewPriority": "HIGH",
        }
        right = {
            "hypothesisClass": "inverter",
            "reviewPriority": "LOW",
        }
        score, matched = module.similarity_score(left, right)
        self.assertEqual(score, 0.35)
        self.assertEqual(matched, ["hypothesisClass"])


if __name__ == "__main__":
    unittest.main()
