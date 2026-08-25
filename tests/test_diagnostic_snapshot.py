from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "services" / "common"))

from fleetmind_common.diagnostic_benchmark_snapshot import (
    load_snapshot,
    save_snapshot_once,
)
from fleetmind_common.diagnostic_dataset import DiagnosticExample


def example(
    vehicle_id: str = "EV-1",
    experiment_id: str = "exp-1",
    label: str = "healthy",
):
    return DiagnosticExample(
        vehicle_id=vehicle_id,
        experiment_id=experiment_id,
        anchor_timestamp=datetime(
            2026, 8, 25, tzinfo=timezone.utc
        ),
        anchor_mileage=10000.0,
        label=label,
        features={
            "ambient_temp_c_mean": 25.0,
            "pump_rpm_mean": 3000.0,
        },
        miles_to_failure=None,
    )


class DiagnosticBenchmarkSnapshotTests(unittest.TestCase):
    def test_snapshot_round_trip_is_experiment_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json.gz"
            saved = save_snapshot_once(
                [example()],
                path,
                {
                    "lineage": "fm-diagnostics-6.3-v1",
                    "experimentId": "exp-1",
                },
            )

            rows, integrity = load_snapshot(
                path,
                expected_sha256=saved["sha256"],
                expected_experiment_id="exp-1",
                expected_lineage="fm-diagnostics-6.3-v1",
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].experiment_id, "exp-1")
            self.assertEqual(rows[0].label, "healthy")
            self.assertEqual(
                integrity["sha256"],
                saved["sha256"],
            )

    def test_snapshot_is_write_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json.gz"
            save_snapshot_once(
                [example()],
                path,
                {"lineage": "fm-diagnostics-6.3-v1"},
            )

            with self.assertRaises(FileExistsError):
                save_snapshot_once(
                    [example(vehicle_id="EV-2")],
                    path,
                    {"lineage": "fm-diagnostics-6.3-v1"},
                )

    def test_snapshot_fails_closed_after_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json.gz"
            saved = save_snapshot_once(
                [example()],
                path,
                {"lineage": "fm-diagnostics-6.3-v1"},
            )

            path.write_bytes(path.read_bytes() + b"tamper")

            with self.assertRaises(Exception):
                load_snapshot(
                    path,
                    expected_sha256=saved["sha256"],
                )

    def test_snapshot_rejects_mixed_experiments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json.gz"

            with self.assertRaises(ValueError):
                save_snapshot_once(
                    [
                        example(
                            vehicle_id="EV-1",
                            experiment_id="exp-1",
                        ),
                        example(
                            vehicle_id="EV-2",
                            experiment_id="exp-2",
                        ),
                    ],
                    path,
                    {"lineage": "fm-diagnostics-6.3-v1"},
                )


if __name__ == "__main__":
    unittest.main()
