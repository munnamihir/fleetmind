from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class FailureTruthExperimentScopeTests(unittest.TestCase):
    def test_failure_event_model_is_experiment_scoped(self):
        source = (
            ROOT / "services/common/fleetmind_common/models.py"
        ).read_text()
        block = source.split(
            "class FailureEvent(Base):", 1
        )[1].split(
            "class MLModelRun(Base):", 1
        )[0]
        self.assertNotIn("unique=True", block)
        self.assertIn(
            'name="uq_failure_events_experiment_vehicle"',
            block,
        )

    def test_worker_lookup_uses_experiment_and_vehicle(self):
        source = (
            ROOT / "services/worker/app/main.py"
        ).read_text()
        block = source.split(
            "def persist_failure(event: dict) -> None:", 1
        )[1].split(
            "def main() -> None:", 1
        )[0]
        self.assertIn(
            "FailureEvent.experiment_id == experiment_id",
            block,
        )
        self.assertIn(
            'FailureEvent.vehicle_id == vehicle["id"]',
            block,
        )

    def test_worker_does_not_move_truth_between_experiments(self):
        source = (
            ROOT / "services/worker/app/main.py"
        ).read_text()
        block = source.split(
            "def persist_failure(event: dict) -> None:", 1
        )[1].split(
            "def main() -> None:", 1
        )[0]
        self.assertNotIn(
            'existing.experiment_id = event.get("experimentId")',
            block,
        )

    def test_schema_migration_converts_global_uniqueness(self):
        source = (
            ROOT / "services/common/fleetmind_common/db.py"
        ).read_text()
        self.assertIn(
            "Phase 6.6.2: failure truth is unique per experiment + vehicle.",
            source,
        )
        self.assertIn(
            "DROP CONSTRAINT failure_events_vehicle_id_key",
            source,
        )
        self.assertIn(
            "DROP INDEX ix_failure_events_vehicle_id",
            source,
        )
        self.assertIn(
            "CREATE INDEX ix_failure_events_vehicle_id",
            source,
        )
        self.assertIn(
            "uq_failure_events_experiment_vehicle",
            source,
        )

    def test_migration_remains_serialized(self):
        source = (
            ROOT / "services/common/fleetmind_common/db.py"
        ).read_text()
        self.assertIn(
            "pg_advisory_xact_lock(68106101)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
