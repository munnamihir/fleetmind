from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "services" / "free_demo_refresh.py").read_text()
WORKFLOW = (ROOT / ".github" / "workflows" / "free-demo-refresh.yml").read_text()


class FreeDemoRefreshContractTests(unittest.TestCase):
    def test_refresh_reuses_existing_simulator_and_worker_logic(self):
        self.assertIn('simulator" / "app" / "sim.py"', SCRIPT)
        self.assertIn('worker" / "app" / "main.py"', SCRIPT)
        self.assertIn("WORKER.persist_telemetry_batch", SCRIPT)
        self.assertIn("WORKER.persist_failure", SCRIPT)
        self.assertIn("SIM.sample_step", SCRIPT)

    def test_refresh_preserves_diagnostic_evidence_gate(self):
        self.assertIn("diagnostic_run.run_once()", SCRIPT)
        self.assertIn('report.get("status") != "trained"', SCRIPT)
        self.assertIn("predeclared diagnostic development gate", SCRIPT)
        self.assertNotIn("DIAGNOSTIC_MIN_TRAIN_EXAMPLES", WORKFLOW)
        self.assertNotIn("DIAGNOSTIC_MIN_VALIDATION_EXAMPLES", WORKFLOW)

    def test_refresh_materializes_operational_layers(self):
        self.assertIn("replace_extended_replay", SCRIPT)
        self.assertIn("diagnostic_event_backfill.materialize_run", SCRIPT)
        self.assertIn("diagnostic_episode_backfill.materialize_run", SCRIPT)
        self.assertIn("diagnostic_case_materialize.materialize_cases", SCRIPT)

    def test_refresh_is_bounded_and_uses_fixed_demo_experiment(self):
        self.assertIn("exp-free-demo-v1", WORKFLOW)
        self.assertIn("FLEETMIND_DEMO_SAMPLES_PER_VEHICLE", WORKFLOW)
        self.assertIn("delete(Telemetry)", SCRIPT)
        self.assertIn("delete(FailureEvent)", SCRIPT)

    def test_refresh_extends_simulated_lifetime_without_weakening_gates(self):
        self.assertIn('FLEETMIND_DEMO_TIME_ACCELERATION: "4800"', WORKFLOW)
        self.assertIn('FLEETMIND_DEMO_TIME_ACCELERATION", "4800"', SCRIPT)
        self.assertIn("EXPECTED_FAILURE_COMPONENTS", SCRIPT)
        self.assertIn("validate_source_failure_coverage", SCRIPT)
        self.assertIn(
            "Increase simulated lifetime rather than weakening diagnostic gates",
            SCRIPT,
        )

    def test_workflow_uses_only_github_runner_and_neon_secret(self):
        self.assertIn("runs-on: ubuntu-latest", WORKFLOW)
        self.assertIn("secrets.FLEETMIND_DEMO_DATABASE_URL", WORKFLOW)
        self.assertNotIn("docker", WORKFLOW.lower())
        self.assertNotIn("redpanda", WORKFLOW.lower())
        self.assertNotIn("kafka", WORKFLOW.lower())

    def test_workflow_is_manual_and_low_frequency_scheduled(self):
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertIn('cron: "17 9 * * 1"', WORKFLOW)


if __name__ == "__main__":
    unittest.main()
