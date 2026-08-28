from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class DiagnosticAPIContractTests(unittest.TestCase):
    def test_api_exposes_expected_read_only_routes(self):
        source = (
            ROOT / "services" / "api" / "app" / "diagnostics.py"
        ).read_text()

        self.assertIn('@router.get("/status")', source)
        self.assertIn('@router.get("/benchmark")', source)
        self.assertIn('@router.get("/vehicles/{vehicle_id}")', source)
        self.assertIn('@router.get("/incidents")', source)

        # The modern diagnostics router intentionally contains
        # human-gated workflow mutation routes from later phases.
        # The original core diagnostic evidence endpoints themselves
        # must remain read-only.
        read_only_routes = (
            "/status",
            "/benchmark",
            "/vehicles/{vehicle_id}",
            "/incidents",
        )

        for route in read_only_routes:
            self.assertNotIn(
                f'@router.post("{route}")',
                source,
            )
            self.assertNotIn(
                f'@router.put("{route}")',
                source,
            )
            self.assertNotIn(
                f'@router.delete("{route}")',
                source,
            )

    def test_vehicle_api_does_not_expose_private_failure_truth(self):
        source = (
            ROOT / "services" / "api" / "app" / "diagnostics.py"
        ).read_text()

        forbidden_response_keys = (
            '"faultFamily"',
            '"failureMode"',
            '"faultCode"',
            '"latentDegradation"',
            '"operatingProfile"',
            '"groundTruth"',
        )

        for key in forbidden_response_keys:
            self.assertNotIn(key, source)

        self.assertIn('"observableEvidence"', source)
        self.assertIn('"interpretationPolicy"', source)

    def test_store_is_experiment_and_run_scoped(self):
        source = (
            ROOT
            / "services"
            / "common"
            / "fleetmind_common"
            / "diagnostic_store.py"
        ).read_text()

        self.assertIn('experiment_id: Mapped[str]', source)
        self.assertIn('"run_id"', source)
        self.assertIn('"vehicle_id"', source)
        self.assertIn(
            'name="uq_diagnostic_prediction_run_vehicle"',
            source,
        )

    def test_main_registers_diagnostic_router(self):
        source = (
            ROOT / "services" / "api" / "app" / "main.py"
        ).read_text()

        self.assertIn(
            "from app.diagnostics import router as diagnostics_router",
            source,
        )
        self.assertIn(
            "app.include_router(diagnostics_router)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
