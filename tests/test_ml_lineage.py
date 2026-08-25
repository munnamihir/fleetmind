import gzip
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "common"))

from fleetmind_common.benchmark_snapshot import (  # noqa: E402
    feature_schema_hash,
    load_snapshot,
    save_snapshot,
)
from fleetmind_common.ml_features import (  # noqa: E402
    FailureTruth,
    FeatureExample,
    TelemetryPoint,
    build_feature_examples,
    latest_monotonic_segment,
)


def point(index: int, mileage: float) -> TelemetryPoint:
    return TelemetryPoint(
        timestamp=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=index),
        vehicle_id="EV-RESET",
        model="SY",
        factory="Austin",
        firmware="2026.32.4",
        pump_revision="CP-17",
        mileage=mileage,
        ambient_temp_c=30.0,
        speed_mph=50.0,
        battery_temp_c=35.0,
        cell_imbalance_v=0.01,
        inverter_temp_c=62.0,
        coolant_temp_c=42.0,
        pump_rpm=2600.0,
        pump_current_a=3.2,
    )


def example(vehicle_id: str, index: int, label: int = 0) -> FeatureExample:
    return FeatureExample(
        vehicle_id=vehicle_id,
        anchor_timestamp=datetime(2026, 8, 24, tzinfo=timezone.utc) + timedelta(minutes=index),
        anchor_mileage=1000.0 + index * 100.0,
        label=label,
        features={
            "pump_current_a_last": 3.0 + index * 0.01,
            "coolant_temp_c_mean": 42.0 + index * 0.1,
        },
        miles_to_failure=500.0 if label else None,
    )


class ExperimentContinuityTests(unittest.TestCase):
    def test_latest_monotonic_segment_drops_prior_mileage_epoch(self):
        rows = [point(i, 70000 + i * 100) for i in range(8)]
        rows += [point(8 + i, 10000 + i * 100) for i in range(8)]
        segment = latest_monotonic_segment(rows, reset_drop_miles=50)
        self.assertEqual(len(segment), 8)
        self.assertEqual(segment[0].mileage, 10000)
        self.assertEqual(segment[-1].mileage, 10700)

    def test_old_failure_truth_is_not_reused_after_simulator_reset(self):
        old = [point(i, 70000 + i * 100) for i in range(8)]
        current = [point(8 + i, 10000 + i * 200) for i in range(16)]
        failure = FailureTruth(
            vehicle_id="EV-RESET",
            failure_mileage=70750.0,
            occurred_at=old[-1].timestamp,
        )
        rows = build_feature_examples(
            {"EV-RESET": old + current},
            {"EV-RESET": failure},
            horizon_miles=600,
            window_size=4,
            stride=1,
            reset_drop_miles=50,
        )
        self.assertTrue(rows)
        self.assertTrue(all(row.anchor_mileage < 20000 for row in rows))
        self.assertTrue(all(row.label == 0 for row in rows))


class BenchmarkSnapshotTests(unittest.TestCase):
    def test_snapshot_round_trip_preserves_exact_examples_and_digest(self):
        rows = [example("EV-1", 1, 0), example("EV-2", 2, 1)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json.gz"
            saved = save_snapshot(rows, path, {"lineage": "fm-ml-test", "seed": 7})
            loaded, integrity = load_snapshot(path, expected_sha256=saved["sha256"])
            self.assertEqual(rows, loaded)
            self.assertEqual(saved["featureSchemaSha256"], integrity["featureSchemaSha256"])
            self.assertEqual(saved["sha256"], integrity["sha256"])

    def test_snapshot_integrity_fails_closed_after_tamper(self):
        rows = [example("EV-1", 1, 1)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json.gz"
            saved = save_snapshot(rows, path, {"lineage": "fm-ml-test"})
            with gzip.open(path, "ab") as handle:
                handle.write(b"tamper")
            with self.assertRaises((ValueError, EOFError, gzip.BadGzipFile)):
                load_snapshot(path, expected_sha256=saved["sha256"])

    def test_feature_schema_hash_is_order_independent_but_schema_sensitive(self):
        first = example("EV-1", 1)
        reordered = FeatureExample(
            vehicle_id=first.vehicle_id,
            anchor_timestamp=first.anchor_timestamp,
            anchor_mileage=first.anchor_mileage,
            label=first.label,
            features={
                "coolant_temp_c_mean": first.features["coolant_temp_c_mean"],
                "pump_current_a_last": first.features["pump_current_a_last"],
            },
            miles_to_failure=first.miles_to_failure,
        )
        changed = FeatureExample(
            vehicle_id=first.vehicle_id,
            anchor_timestamp=first.anchor_timestamp,
            anchor_mileage=first.anchor_mileage,
            label=first.label,
            features={**first.features, "new_feature": 1.0},
            miles_to_failure=first.miles_to_failure,
        )
        self.assertEqual(feature_schema_hash([first]), feature_schema_hash([reordered]))
        self.assertNotEqual(feature_schema_hash([first]), feature_schema_hash([changed]))


if __name__ == "__main__":
    unittest.main()
