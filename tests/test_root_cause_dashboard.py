from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]

class RootCauseDashboardContractTests(unittest.TestCase):
    def test_api_has_exact_run_summary(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()
        self.assertIn('@router.get("/summary")', source)
        self.assertIn("DiagnosticPrediction.run_id == run.id", source)
        self.assertIn('"highConfidenceIncidents"', source)
        self.assertIn('"interpretationPolicy"', source)

    def test_dashboard_uses_real_diagnostic_endpoints(self):
        source = (ROOT / "web/src/RootCauseDashboard.tsx").read_text()
        for path in (
            "/api/v1/diagnostics/summary",
            "/api/v1/diagnostics/status",
            "/api/v1/diagnostics/benchmark",
            "/api/v1/diagnostics/incidents",
            "/api/v1/diagnostics/vehicles/",
        ):
            self.assertIn(path, source)

    def test_dashboard_semantics_are_evidence_safe(self):
        source = (ROOT / "web/src/RootCauseDashboard.tsx").read_text()
        self.assertIn("OBSERVED SIGNALS", source)
        self.assertIn("not feature-attribution scores or causal proof", source)
        self.assertIn("not failure ground truth", source)

    def test_dashboard_surfaces_locked_benchmark_limitations(self):
        source = (ROOT / "web/src/RootCauseDashboard.tsx").read_text()
        self.assertIn("Known benchmark limitation", source)
        self.assertIn("weakestClass", source)
        self.assertIn("metricsPublishable", source)
        self.assertIn("SELECTED ON VALIDATION", source)

    def test_app_registers_root_cause_page(self):
        source = (ROOT / "web/src/App.tsx").read_text()
        self.assertIn("RootCauseDashboard", source)
        self.assertIn("'diagnostics'", source)
        self.assertIn("setPage('diagnostics')", source)
        self.assertIn("<RootCauseDashboard />", source)

if __name__ == "__main__":
    unittest.main()
