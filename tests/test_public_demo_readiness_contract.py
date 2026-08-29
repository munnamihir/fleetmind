from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DEMO = (ROOT / "web" / "src" / "FleetMindPublicDemo.tsx").read_text()
COLD_START = (ROOT / "web" / "src" / "FleetMindExperienceV2.tsx").read_text()
MAIN = (ROOT / "web" / "src" / "main.tsx").read_text()
PORTAL = (ROOT / "web" / "src" / "FleetMindDemoBannerPortal.tsx").read_text()


class PublicDemoReadinessContractTests(unittest.TestCase):
    def test_synthetic_demo_identity_is_explicit(self):
        self.assertIn("SYNTHETIC DEMO", PUBLIC_DEMO)
        self.assertIn("not live vehicle telemetry", PUBLIC_DEMO)
        self.assertIn("physical failure probability", PUBLIC_DEMO)
        self.assertIn("causal proof", PUBLIC_DEMO)

    def test_provenance_uses_persisted_run_creation_time(self):
        self.assertIn("status?.createdAt", PUBLIC_DEMO)
        self.assertIn("Experiment", PUBLIC_DEMO)
        self.assertIn("Run", PUBLIC_DEMO)
        self.assertIn("Lineage", PUBLIC_DEMO)
        self.assertIn("/api/v1/diagnostics/status", PUBLIC_DEMO)

    def test_demo_banner_stays_in_normal_dashboard_flow(self):
        self.assertIn("tabs.before(nextHost)", PORTAL)
        self.assertIn("FleetMindDemoBannerPortal", MAIN)
        self.assertNotIn("position: sticky", PORTAL)
        self.assertNotIn("position: fixed", PORTAL)

    def test_free_service_wake_state_is_not_immediately_offline(self):
        self.assertIn("apiWaking", COLD_START)
        self.assertIn("WAKING API", COLD_START)
        self.assertIn("WAKING FREE SERVICE", COLD_START)
        self.assertIn("2200", COLD_START)

    def test_public_landing_page_precedes_command_center(self):
        self.assertIn("PUBLIC RESEARCH DEMO", PUBLIC_DEMO)
        self.assertIn("From fleet signal to human-governed outcome.", PUBLIC_DEMO)
        self.assertIn("Take the guided demo", PUBLIC_DEMO)
        self.assertIn("Enter command center", PUBLIC_DEMO)
        self.assertIn("sessionStorage", PUBLIC_DEMO)

    def test_guided_story_covers_evidence_to_outcomes(self):
        for expected in (
            "VEHICLE EVIDENCE",
            "COMPETING HYPOTHESES",
            "INVESTIGATION CASE",
            "HUMAN-GOVERNED ACTION",
            "OBSERVED OUTCOME",
            "Investigate",
            "Cases",
            "Actions & Outcomes",
            "Recommendations",
            "Outcomes",
        ):
            self.assertIn(expected, PUBLIC_DEMO)

    def test_guided_story_does_not_mutate_workflow(self):
        self.assertNotIn("/approve", PUBLIC_DEMO)
        self.assertNotIn("/execute", PUBLIC_DEMO)
        self.assertNotIn("materialize: true", PUBLIC_DEMO)
        self.assertNotIn("method: 'POST'", PUBLIC_DEMO)
        self.assertNotIn('method: "POST"', PUBLIC_DEMO)


if __name__ == "__main__":
    unittest.main()
