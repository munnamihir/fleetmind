from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "services" / "common"))

from fleetmind_common.diagnostics import (
    DIAGNOSTIC_FEATURE_SCHEMA_VERSION,
    DiagnosticTelemetryPoint,
    assert_observable_only_features,
    diagnostic_feature_schema_hash,
    extract_diagnostic_features,
)


def make_window(
    *,
    ambient_offset: float = 0.0,
    coolant_bias_growth: float = 0.0,
    pump_degradation: float = 0.0,
    inverter_degradation: float = 0.0,
    motor_degradation: float = 0.0,
):
    start = datetime(2026, 8, 25, tzinfo=timezone.utc)
    points = []

    for index in range(12):
        progress = index / 11.0
        mileage = 50000.0 + index * 75.0
        load = 65.0 + index * 9.0

        ambient = 24.0 + ambient_offset + index * 0.03
        battery = ambient + 11.0 + load * 0.018
        inverter = ambient + 18.0 + load * 0.045
        motor = ambient + 20.0 + load * 0.05
        coolant = ambient + 14.0 + load * 0.025

        inverter += inverter_degradation * progress * 16.0
        motor += motor_degradation * progress * 18.0
        coolant += coolant_bias_growth * progress * 20.0

        pump_rpm = 3200.0 - pump_degradation * progress * 850.0
        pump_current = 3.1 + pump_degradation * progress * 2.4

        points.append(
            DiagnosticTelemetryPoint(
                timestamp=start + timedelta(seconds=index * 5),
                vehicle_id="EV-TEST-001",
                experiment_id="exp-test",
                mileage=mileage,
                ambient_temp_c=ambient,
                speed_mph=42.0 + index,
                soc_pct=82.0 - index * 0.7,
                pack_voltage_v=402.0 - load * 0.04,
                pack_current_a=load,
                battery_temp_c=battery,
                cell_imbalance_v=0.006 + index * 0.00005,
                motor_temp_c=motor,
                inverter_temp_c=inverter,
                motor_rpm=4200.0 + index * 90.0,
                coolant_temp_c=coolant,
                pump_rpm=pump_rpm,
                pump_current_a=pump_current,
            )
        )

    return points


class DiagnosticFeatureTests(unittest.TestCase):
    def test_schema_version_is_explicit(self):
        self.assertEqual(
            DIAGNOSTIC_FEATURE_SCHEMA_VERSION,
            "fm-diagnostics-features-6.2-v1",
        )

    def test_feature_vector_contains_only_numeric_observable_features(self):
        features = extract_diagnostic_features(make_window())

        self.assertGreaterEqual(len(features), 100)
        self.assertTrue(all(isinstance(value, float) for value in features.values()))

        forbidden_fragments = (
            "vehicle_id",
            "experiment_id",
            "firmware",
            "pump_revision",
            "risk_score",
            "status",
            "fault",
            "failure",
            "operating_profile",
            "latent",
            "component",
        )
        for key in features:
            for fragment in forbidden_fragments:
                self.assertNotIn(fragment, key.lower())

    def test_leakage_guard_rejects_private_truth(self):
        with self.assertRaises(ValueError):
            assert_observable_only_features(
                {
                    "coolant_temp_c_mean": 40.0,
                    "fault_family": "coolant_pump",
                }
            )

        with self.assertRaises(ValueError):
            assert_observable_only_features(
                {
                    "motor_temp_c_mean": 50.0,
                    "operating_profile": "high_load",
                }
            )

    def test_schema_hash_is_order_independent(self):
        features = extract_diagnostic_features(make_window())
        reversed_features = dict(reversed(list(features.items())))

        self.assertEqual(
            diagnostic_feature_schema_hash(features),
            diagnostic_feature_schema_hash(reversed_features),
        )

    def test_environmental_heat_is_removed_by_ambient_adjustment(self):
        normal = extract_diagnostic_features(make_window(ambient_offset=0.0))
        hot = extract_diagnostic_features(make_window(ambient_offset=20.0))

        self.assertAlmostEqual(
            normal["coolant_ambient_delta_c_mean"],
            hot["coolant_ambient_delta_c_mean"],
            places=8,
        )
        self.assertAlmostEqual(
            normal["inverter_ambient_delta_c_mean"],
            hot["inverter_ambient_delta_c_mean"],
            places=8,
        )
        self.assertAlmostEqual(
            normal["motor_ambient_delta_c_mean"],
            hot["motor_ambient_delta_c_mean"],
            places=8,
        )

    def test_pump_degradation_changes_electromechanical_efficiency(self):
        healthy = extract_diagnostic_features(make_window())
        degraded = extract_diagnostic_features(
            make_window(pump_degradation=1.0)
        )

        self.assertGreater(
            degraded["pump_current_per_1k_rpm_last"],
            healthy["pump_current_per_1k_rpm_last"],
        )
        self.assertLess(
            degraded["pump_rpm_per_amp_last"],
            healthy["pump_rpm_per_amp_last"],
        )
        self.assertLess(
            degraded["pump_rpm_slope_per_1k_mi"],
            healthy["pump_rpm_slope_per_1k_mi"],
        )

    def test_coolant_sensor_drift_becomes_thermally_isolated(self):
        healthy = extract_diagnostic_features(make_window())
        drift = extract_diagnostic_features(
            make_window(coolant_bias_growth=1.0)
        )

        self.assertGreater(
            drift["coolant_peer_residual_c_last"],
            healthy["coolant_peer_residual_c_last"] + 10.0,
        )
        self.assertGreater(
            drift["thermal_peer_spread_c_last"],
            healthy["thermal_peer_spread_c_last"],
        )

    def test_inverter_and_motor_fault_signatures_separate(self):
        inverter = extract_diagnostic_features(
            make_window(inverter_degradation=1.0)
        )
        motor = extract_diagnostic_features(
            make_window(motor_degradation=1.0)
        )

        self.assertGreater(
            inverter["inverter_ambient_delta_c_last"],
            motor["inverter_ambient_delta_c_last"],
        )
        self.assertGreater(
            motor["motor_ambient_delta_c_last"],
            inverter["motor_ambient_delta_c_last"],
        )
        self.assertLess(
            inverter["motor_inverter_delta_c_last"],
            motor["motor_inverter_delta_c_last"],
        )

    def test_window_rejects_mixed_experiments_and_mileage_resets(self):
        mixed = list(make_window())
        mixed[-1] = DiagnosticTelemetryPoint(
            **{
                **mixed[-1].__dict__,
                "experiment_id": "exp-other",
            }
        )
        with self.assertRaises(ValueError):
            extract_diagnostic_features(mixed)

        reset = list(make_window())
        reset[-1] = DiagnosticTelemetryPoint(
            **{
                **reset[-1].__dict__,
                "mileage": reset[-2].mileage - 100.0,
            }
        )
        with self.assertRaises(ValueError):
            extract_diagnostic_features(reset)


if __name__ == "__main__":
    unittest.main()
