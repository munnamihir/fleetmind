import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MAIN = (ROOT / "services/api/app/main.py").read_text()
COMPLETION = (ROOT / "services/api/app/completion.py").read_text()
PLATFORM = (ROOT / "services/api/app/platform.py").read_text()
STORE = (
    ROOT / "services/common/fleetmind_common/platform_store.py"
).read_text()
DB = (ROOT / "services/common/fleetmind_common/db.py").read_text()
FLEET_COMMAND = (ROOT / "web/src/FleetCommandOperations.tsx").read_text()
ROOT_CAUSE = (ROOT / "web/src/RootCauseDashboard.tsx").read_text()
DASHBOARD_TABS = (ROOT / "web/src/DashboardPageTabs.tsx").read_text()


class RemainingPhaseContractTests(unittest.TestCase):
    def test_api_routers_are_mounted(self):
        self.assertIn("completion_router", MAIN)
        self.assertIn("platform_router", MAIN)
        self.assertIn("configure_observability(app)", MAIN)

    def test_phase_82_routes(self):
        for route in (
            '/closed-loop/outcomes/evaluate',
            '/closed-loop/outcomes/summary',
            '/closed-loop/outcomes',
            '/closed-loop/effectiveness',
        ):
            self.assertIn(route, COMPLETION)

    def test_phase_84_85_routes(self):
        for route in (
            '/closed-loop/policies/bootstrap',
            '/closed-loop/policies/{policy_id}/evaluate',
            '/closed-loop/policies/{policy_id}/promote',
            '/closed-loop/policies/rollback',
            '/closed-loop/shadow-experiments',
        ):
            self.assertIn(route, COMPLETION)

    def test_phase_9_platform_routes(self):
        for route in (
            '/status',
            '/slo',
            '/model-registry',
            '/assets/plugins',
            '/assets/summary',
        ):
            self.assertIn(route, PLATFORM)

    def test_outcome_and_policy_identities_are_unique(self):
        self.assertIn(
            'uq_diagnostic_recommendation_outcome_evaluation_key',
            STORE,
        )
        self.assertIn(
            'uq_diagnostic_recommendation_policy_key_version',
            STORE,
        )
        self.assertIn(
            'uq_diagnostic_policy_evaluation_key',
            STORE,
        )
        self.assertIn(
            'uq_diagnostic_shadow_experiment_key',
            STORE,
        )

    def test_existing_recommendation_materialization_is_selected_vehicle_only(self):
        self.assertIn(
            "materialize\n                ? [selectedVehicleId]\n                : null",
            FLEET_COMMAND,
        )

    def test_outcomes_are_exposed_in_closed_loop_ui(self):
        self.assertIn("'OUTCOMES'", FLEET_COMMAND)
        self.assertIn("<ClosedLoopOutcomesPanel", FLEET_COMMAND)

    def test_platform_console_is_lazy_root_view(self):
        self.assertIn(
            "activeView === 'platform'",
            ROOT_CAUSE,
        )
        self.assertIn(
            "<PlatformCompletionConsole",
            ROOT_CAUSE,
        )
        self.assertIn(
            "{ id: 'platform', label: 'Platform' }",
            DASHBOARD_TABS,
        )

    def test_db_pool_is_not_inflated_as_workaround(self):
        self.assertIn(
            "create_engine(DATABASE_URL, pool_pre_ping=True)",
            DB,
        )
        self.assertNotIn("pool_size=20", DB)
        self.assertNotIn("max_overflow=30", DB)

    def test_phase_9_infrastructure_exists(self):
        required = (
            "docker-compose.platform.yml",
            "infra/observability/prometheus.yml",
            "infra/observability/grafana/dashboards/fleetmind-platform.json",
            "deploy/helm/fleetmind/Chart.yaml",
            "deploy/helm/fleetmind/templates/migration-job.yaml",
            "tools/kafka_load_generator.py",
            "tools/backpressure_replay_test.sh",
            "tools/disaster_recovery_smoke.sh",
            "services/archive/app/main.py",
            "services/asset_worker/app/main.py",
            "services/asset_simulator/app/main.py",
        )
        for rel in required:
            self.assertTrue((ROOT / rel).exists(), rel)

    def test_truth_boundaries_remain_explicit(self):
        self.assertIn(
            '"maintenanceCausalityEstablished": False',
            COMPLETION,
        )
        self.assertIn(
            '"productionBehaviorChanged": False',
            COMPLETION,
        )
        self.assertIn(
            '"hundredKEventsPerSecondEmpiricallyVerified": False',
            PLATFORM,
        )
        self.assertIn(
            '"productionSLOsClaimedAchieved": False',
            PLATFORM,
        )


if __name__ == "__main__":
    unittest.main()
