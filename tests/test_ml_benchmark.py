import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "common"))

from fleetmind_common.ml_features import (  # noqa: E402
    FeatureExample,
    frozen_partition,
    split_examples_frozen_benchmark,
)


def example(vehicle_id: str, index: int, label: int = 0) -> FeatureExample:
    return FeatureExample(
        vehicle_id=vehicle_id,
        anchor_timestamp=datetime(2026, 8, 24, tzinfo=timezone.utc) + timedelta(minutes=index),
        anchor_mileage=1000.0 + index * 100.0,
        label=label,
        features={"pump_current_a_last": 3.0 + index * 0.01},
        miles_to_failure=500.0 if label else None,
    )


class FrozenBenchmarkTests(unittest.TestCase):
    def test_partition_is_stable_and_label_agnostic(self):
        ids = [f"EV-{idx:06d}" for idx in range(1, 501)]
        first = {vehicle_id: frozen_partition(vehicle_id) for vehicle_id in ids}
        second = {vehicle_id: frozen_partition(vehicle_id) for vehicle_id in reversed(ids)}
        self.assertEqual(first, second)
        self.assertTrue({"train", "validation", "benchmark"}.issubset(set(first.values())))

    def test_frozen_benchmark_never_overlaps_development(self):
        rows = []
        for vehicle_idx in range(1, 220):
            vehicle_id = f"EV-{vehicle_idx:06d}"
            for index in range(8):
                rows.append(example(vehicle_id, index, label=1 if index == 6 and vehicle_idx % 7 == 0 else 0))

        split = split_examples_frozen_benchmark(rows)
        train_ids = {row.vehicle_id for row in split.train}
        validation_ids = {row.vehicle_id for row in split.validation}
        benchmark_ids = {row.vehicle_id for row in split.benchmark}

        self.assertFalse(train_ids & validation_ids)
        self.assertFalse(train_ids & benchmark_ids)
        self.assertFalse(validation_ids & benchmark_ids)
        self.assertTrue(train_ids and validation_ids and benchmark_ids)
        self.assertTrue(all(frozen_partition(vehicle_id) == "benchmark" for vehicle_id in benchmark_ids))

    def test_benchmark_membership_does_not_change_when_labels_change(self):
        healthy_rows = []
        changed_rows = []
        for vehicle_idx in range(1, 180):
            vehicle_id = f"EV-{vehicle_idx:06d}"
            for index in range(6):
                healthy_rows.append(example(vehicle_id, index, label=0))
                changed_rows.append(example(vehicle_id, index, label=1 if index == 5 and vehicle_idx % 5 == 0 else 0))

        healthy_split = split_examples_frozen_benchmark(healthy_rows)
        changed_split = split_examples_frozen_benchmark(changed_rows)
        healthy_ids = {row.vehicle_id for row in healthy_split.benchmark}
        changed_ids = {row.vehicle_id for row in changed_split.benchmark}
        self.assertEqual(healthy_ids, changed_ids)


if __name__ == "__main__":
    unittest.main()
