import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "services" / "api" / "app" / "diagnostics.py"
STORE = ROOT / "services" / "common" / "fleetmind_common" / "diagnostic_store.py"


class ClosedLoopMaterializationConcurrencyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = DIAGNOSTICS.read_text()
        cls.store = STORE.read_text()
        cls.section = cls.api.split(
            "# Phase 8.0 — Closed-Loop Operations Foundation",
            1,
        )[1]

    def test_database_key_is_unique(self):
        self.assertIn(
            '"uq_diagnostic_operational_"',
            self.store,
        )
        self.assertIn(
            '"recommendation_key"',
            self.store,
        )

    def test_bulk_lookup_preserves_fast_idempotent_path(self):
        self.assertIn(
            "DiagnosticOperationalRecommendation.recommendation_key.in_(",
            self.section,
        )

    def test_concurrent_insert_uses_savepoint(self):
        self.assertIn(
            "from sqlalchemy.exc import IntegrityError",
            self.api,
        )
        self.assertIn(
            "with db.begin_nested():",
            self.section,
        )
        self.assertIn(
            "except IntegrityError:",
            self.section,
        )

    def test_concurrent_winner_is_reloaded_as_existing(self):
        self.assertIn(
            "DiagnosticOperationalRecommendation.recommendation_key\n                    == key",
            self.section,
        )
        self.assertIn(
            "existing_by_key[key] = existing",
            self.section,
        )

    def test_new_key_is_registered_before_next_candidate(self):
        self.assertIn(
            "existing_by_key[key] = row",
            self.section,
        )

    def test_created_activity_remains_non_executing(self):
        for marker in (
            '"automaticApproval": False',
            '"automaticExecution": False',
            '"physicalAction": False',
        ):
            self.assertIn(marker, self.section)


if __name__ == "__main__":
    unittest.main()
