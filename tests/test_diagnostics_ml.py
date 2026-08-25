from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "services" / "common"))
sys.path.insert(0, str(ROOT / "services" / "ml" / "app"))

from diagnostic_models import (
    XGBOOST_AVAILABLE,
    TransparentDiagnosticBaseline,
    evaluate_diagnostic_probabilities,
    fit_compare_diagnostic_models,
    predict_ranked_hypotheses,
)
from fleetmind_common.diagnostic_dataset import (
    DIAGNOSTIC_CLASSES,
    DiagnosticExample,
    DiagnosticFailureTruth,
    build_diagnostic_examples,
    diagnostic_benchmark_member,
    diagnostic_feature_schema,
    qualify_diagnostic_benchmark,
    split_diagnostic_examples,
)
from fleetmind_common.diagnostics import (
    DiagnosticTelemetryPoint,
    extract_diagnostic_features,
)


def make_window(
    vehicle_id: str,
    experiment_id: str,
    class_name: str,
    variant: int,
):
    start = datetime(2026, 8, 25, tzinfo=timezone.utc)
    points = []

    for index in range(12):
        progress = index / 11.0
        mileage = 30000.0 + variant * 15.0 + index * 90.0
        load = 70.0 + index * 8.0 + variant * 0.7

        ambient = 23.0 + variant * 0.04
        battery = ambient + 11.0 + load * 0.018
        inverter = ambient + 17.0 + load * 0.040
        motor = ambient + 20.0 + load * 0.045
        coolant = ambient + 14.0 + load * 0.024
        imbalance = 0.006 + index * 0.00004
        pump_rpm = 3200.0
        pump_current = 3.0

        if class_name == "coolant_pump":
            pump_rpm -= progress * (700.0 + variant * 3.0)
            pump_current += progress * (2.0 + variant * 0.01)
            coolant += progress * 8.0
            battery += progress * 3.0
        elif class_name == "battery_pack":
            imbalance += progress * (0.030 + variant * 0.0001)
            battery += progress * 9.0
        elif class_name == "inverter":
            inverter += progress * 18.0
            coolant += progress * 5.0
            motor += progress * 3.0
        elif class_name == "traction_motor":
            motor += progress * 20.0
            inverter += progress * 4.0
        elif class_name == "coolant_temp_sensor":
            coolant += progress * 22.0

        points.append(
            DiagnosticTelemetryPoint(
                timestamp=start + timedelta(seconds=index * 5 + variant),
                vehicle_id=vehicle_id,
                experiment_id=experiment_id,
                mileage=mileage,
                ambient_temp_c=ambient,
                speed_mph=45.0 + index * 0.7,
                soc_pct=82.0 - index * 0.6,
                pack_voltage_v=402.0 - load * 0.035,
                pack_current_a=load,
                battery_temp_c=battery,
                cell_imbalance_v=imbalance,
                motor_temp_c=motor,
                inverter_temp_c=inverter,
                motor_rpm=4300.0 + index * 95.0,
                coolant_temp_c=coolant,
                pump_rpm=pump_rpm,
                pump_current_a=pump_current,
            )
        )

    return points


def make_examples(per_class: int = 12):
    examples = []
    experiment_id = "exp-diagnostic-test"

    for class_index, class_name in enumerate(DIAGNOSTIC_CLASSES):
        for vehicle_index in range(per_class):
            vehicle_id = f"{class_name}-{vehicle_index:03d}"
            features = extract_diagnostic_features(
                make_window(
                    vehicle_id,
                    experiment_id,
                    class_name,
                    vehicle_index,
                )
            )
            examples.append(
                DiagnosticExample(
                    vehicle_id=vehicle_id,
                    experiment_id=experiment_id,
                    anchor_timestamp=datetime(
                        2026,
                        8,
                        25,
                        tzinfo=timezone.utc,
                    ),
                    anchor_mileage=31000.0,
                    label=class_name,
                    features=features,
                    miles_to_failure=800.0 if class_name != "healthy" else None,
                )
            )

    return examples


class DiagnosticDatasetTests(unittest.TestCase):
    def test_benchmark_membership_is_label_agnostic_and_stable(self):
        vehicle_id = "EV-000123"
        first = diagnostic_benchmark_member(vehicle_id)
        second = diagnostic_benchmark_member(vehicle_id)
        self.assertEqual(first, second)

    def test_split_is_vehicle_isolated(self):
        examples = []
        for example in make_examples(8):
            examples.extend([example, example])

        split = split_diagnostic_examples(examples)

        train = {example.vehicle_id for example in split.train}
        validation = {example.vehicle_id for example in split.validation}
        benchmark = {example.vehicle_id for example in split.benchmark}

        self.assertFalse(train & validation)
        self.assertFalse(train & benchmark)
        self.assertFalse(validation & benchmark)

    def test_right_censoring_and_multiclass_labeling(self):
        experiment_id = "exp-build-test"
        vehicle_id = "EV-BATT-001"
        start = datetime(2026, 8, 25, tzinfo=timezone.utc)

        points = []
        for index in range(60):
            base = make_window(
                vehicle_id,
                experiment_id,
                "battery_pack",
                1,
            )[index % 12]
            points.append(
                DiagnosticTelemetryPoint(
                    **{
                        **base.__dict__,
                        "timestamp": start + timedelta(seconds=index * 5),
                        "mileage": 40000.0 + index * 100.0,
                    }
                )
            )

        failure = DiagnosticFailureTruth(
            vehicle_id=vehicle_id,
            experiment_id=experiment_id,
            component="battery_pack",
            failure_mileage=45500.0,
            occurred_at=start + timedelta(seconds=500),
        )

        examples = build_diagnostic_examples(
            {vehicle_id: points},
            [failure],
            experiment_id=experiment_id,
            horizon_miles=2500.0,
            window_size=12,
            stride=4,
            max_examples_per_vehicle=32,
        )

        labels = {example.label for example in examples}
        self.assertIn("healthy", labels)
        self.assertIn("battery_pack", labels)
        self.assertTrue(
            all(
                example.anchor_mileage <= failure.failure_mileage
                for example in examples
            )
        )

    def test_schema_consistency(self):
        examples = make_examples(4)
        names, schema_hash = diagnostic_feature_schema(examples)
        self.assertGreater(len(names), 100)
        self.assertEqual(len(schema_hash), 64)

    def test_benchmark_gate_fails_closed_when_classes_are_missing(self):
        examples = [
            example
            for example in make_examples(5)
            if example.label in {"healthy", "coolant_pump"}
        ]
        qualification = qualify_diagnostic_benchmark(
            examples,
            min_examples=1,
            min_examples_per_class=1,
            min_vehicles_per_class=1,
        )
        self.assertEqual(
            qualification.status,
            "insufficient_evidence",
        )
        self.assertTrue(
            any(
                "battery_pack" in reason
                for reason in qualification.reasons
            )
        )


class DiagnosticModelTests(unittest.TestCase):
    @unittest.skipUnless(
        XGBOOST_AVAILABLE,
        "xgboost is not installed in the local Python environment",
    )
    def test_all_three_models_train_and_produce_multiclass_metrics(self):
        examples = make_examples(18)

        # Deterministic per-class vehicle split for this unit test. Production
        # frozen benchmark behavior is tested independently above.
        train = []
        validation = []
        for example in examples:
            vehicle_index = int(example.vehicle_id.rsplit("-", 1)[1])
            if vehicle_index < 12:
                train.append(example)
            else:
                validation.append(example)

        baseline, logistic, xgb, comparison = fit_compare_diagnostic_models(
            train,
            validation,
        )

        self.assertIsInstance(
            baseline,
            TransparentDiagnosticBaseline,
        )
        self.assertEqual(
            comparison.feature_names,
            diagnostic_feature_schema(train)[0],
        )

        for metrics in (
            comparison.baseline_metrics,
            comparison.logistic_metrics,
            comparison.xgboost_metrics,
        ):
            self.assertGreaterEqual(metrics.macro_f1, 0.0)
            self.assertLessEqual(metrics.macro_f1, 1.0)
            self.assertGreaterEqual(metrics.top2_accuracy, 0.0)
            self.assertLessEqual(metrics.top2_accuracy, 1.0)
            self.assertEqual(
                len(metrics.confusion_matrix),
                len(DIAGNOSTIC_CLASSES),
            )

        self.assertIn(
            comparison.champion,
            {
                "transparent_baseline",
                "multinomial_logistic",
                "xgboost_multiclass",
            },
        )

        ranked = predict_ranked_hypotheses(
            logistic,
            validation[:3],
            feature_names=comparison.feature_names,
            top_k=2,
        )
        self.assertEqual(len(ranked), 3)
        self.assertTrue(
            all(len(hypotheses) == 2 for hypotheses in ranked)
        )

    def test_probability_metrics_support_competing_hypotheses(self):
        examples = make_examples(1)
        probability = 1.0 / len(DIAGNOSTIC_CLASSES)
        probabilities = [
            [probability] * len(DIAGNOSTIC_CLASSES)
            for _ in examples
        ]

        import numpy as np

        metrics = evaluate_diagnostic_probabilities(
            examples,
            np.asarray(probabilities),
        )
        self.assertGreaterEqual(metrics.top2_accuracy, 0.0)
        self.assertLessEqual(metrics.top2_accuracy, 1.0)
        self.assertGreater(metrics.multiclass_brier, 0.0)


if __name__ == "__main__":
    unittest.main()
