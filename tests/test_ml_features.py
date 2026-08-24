import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "common"))

from fleetmind_common.ml_features import (  # noqa: E402
    FailureTruth,
    FeatureExample,
    TelemetryPoint,
    assert_no_leakage,
    build_feature_examples,
    extract_window_features,
    split_examples_time_and_vehicle,
    vehicle_partition,
)


def point(vehicle_id: str, index: int, mileage: float, pump_current: float = 3.0) -> TelemetryPoint:
    return TelemetryPoint(
        timestamp=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=index),
        vehicle_id=vehicle_id,
        model="SY",
        factory="Austin",
        firmware="2026.32.4",
        pump_revision="CP-17",
        mileage=mileage,
        ambient_temp_c=34.0,
        speed_mph=55.0,
        battery_temp_c=36.0 + index * 0.1,
        cell_imbalance_v=0.012,
        inverter_temp_c=65.0,
        coolant_temp_c=43.0 + index * 0.2,
        pump_rpm=2700.0 - index * 10,
        pump_current_a=pump_current + index * 0.03,
    )


class MLFeatureTests(unittest.TestCase):
    def test_feature_window_excludes_leakage_fields(self):
        features = extract_window_features([point("EV-1", i, 1000 + i * 100) for i in range(12)])
        assert_no_leakage(features)
        self.assertNotIn("risk_score", features)
        self.assertNotIn("status", features)
        self.assertNotIn("failure_mileage", features)
        self.assertIn("pump_current_a_slope_per_1k_mi", features)

    def test_positive_label_uses_only_future_failure_horizon(self):
        points = [point("EV-1", i, 1000 + i * 250) for i in range(30)]
        failure = FailureTruth("EV-1", failure_mileage=7600.0, occurred_at=points[-1].timestamp)
        rows = build_feature_examples(
            {"EV-1": points},
            {"EV-1": failure},
            horizon_miles=1500,
            window_size=6,
            stride=1,
        )
        self.assertTrue(any(row.label == 1 for row in rows))
        self.assertTrue(all(row.anchor_mileage < failure.failure_mileage for row in rows))
        self.assertTrue(all(row.label == (row.miles_to_failure <= 1500) for row in rows))

    def test_right_censored_negative_windows_are_dropped(self):
        points = [point("EV-2", i, 1000 + i * 100) for i in range(20)]
        rows = build_feature_examples(
            {"EV-2": points},
            {},
            horizon_miles=1000,
            window_size=5,
            stride=1,
        )
        latest_mileage = points[-1].mileage
        self.assertTrue(rows)
        self.assertTrue(all(latest_mileage - row.anchor_mileage >= 1000 for row in rows))
        self.assertTrue(all(row.label == 0 for row in rows))

    def test_vehicle_partition_is_stable_and_disjoint(self):
        ids = [f"EV-{i:06d}" for i in range(1, 300)]
        partitions = {vehicle_id: vehicle_partition(vehicle_id) for vehicle_id in ids}
        self.assertEqual(partitions, {vehicle_id: vehicle_partition(vehicle_id) for vehicle_id in ids})
        self.assertTrue({"train", "validation", "test"}.issubset(set(partitions.values())))

    def test_split_is_vehicle_isolated_and_walk_forward(self):
        base = datetime(2026, 8, 24, tzinfo=timezone.utc)
        examples = []
        for vehicle_idx in range(1, 120):
            vehicle_id = f"EV-{vehicle_idx:06d}"
            for time_idx in range(10):
                examples.append(
                    FeatureExample(
                        vehicle_id=vehicle_id,
                        anchor_timestamp=base + timedelta(minutes=time_idx),
                        anchor_mileage=1000 + time_idx * 100,
                        label=1 if time_idx == 8 else 0,
                        features={"pump_current_a_last": 3.0},
                        miles_to_failure=500.0 if time_idx == 8 else None,
                    )
                )
        split = split_examples_time_and_vehicle(examples)
        train_ids = {row.vehicle_id for row in split.train}
        val_ids = {row.vehicle_id for row in split.validation}
        test_ids = {row.vehicle_id for row in split.test}
        self.assertFalse(train_ids & val_ids)
        self.assertFalse(train_ids & test_ids)
        self.assertFalse(val_ids & test_ids)
        self.assertTrue(split.train and split.validation and split.test)
        # Stratification is performed at the vehicle level, never at the row level.
        positive_vehicles = {row.vehicle_id for row in examples if row.label == 1}
        if len(positive_vehicles) >= 3:
            self.assertTrue(any(row.label == 1 for row in split.validation))
            self.assertTrue(any(row.label == 1 for row in split.test))
        # Held-out evaluation uses late-life windows from each validation/test vehicle.
        for rows in (split.validation, split.test):
            by_vehicle = {}
            for row in rows:
                by_vehicle.setdefault(row.vehicle_id, []).append(row)
            self.assertTrue(all(vehicle_rows == sorted(vehicle_rows, key=lambda item: item.anchor_timestamp) for vehicle_rows in by_vehicle.values()))


if __name__ == "__main__":
    unittest.main()
