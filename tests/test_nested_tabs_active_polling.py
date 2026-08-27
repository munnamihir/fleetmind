import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / 'web/src/App.tsx').read_text()
ROOT_CAUSE = (ROOT / 'web/src/RootCauseDashboard.tsx').read_text()
FLEET_COMMAND = (ROOT / 'web/src/FleetCommandOperations.tsx').read_text()
TABS = (ROOT / 'web/src/DashboardPageTabs.tsx').read_text()
CSS = (ROOT / 'web/src/DashboardPageTabs.css').read_text()


class NestedTabsActivePollingTests(unittest.TestCase):
    def test_app_polls_by_active_left_page(self):
        self.assertIn("} else if (page === 'firmware') {", APP)
        self.assertIn("} else if (page === 'ml') {", APP)
        self.assertIn('  }, [page]);', APP)
        self.assertNotIn(
            'const [s, a, c, r, f, fo, fr, ms, mp] = await Promise.all',
            APP,
        )

    def test_app_owns_controlled_nested_view(self):
        self.assertIn('dashboardViewByPage', APP)
        self.assertIn('data-dashboard-view={activeDashboardView}', APP)
        self.assertIn('active={activeDashboardView}', APP)
        self.assertIn('DEFAULT_DASHBOARD_VIEW', APP)

    def test_root_cause_receives_active_view(self):
        self.assertIn("activeView = 'overview'", ROOT_CAUSE)
        self.assertIn('  }, [activeView]);', ROOT_CAUSE)

    def test_root_parent_fetches_only_needed_data(self):
        self.assertIn('const needsSummary = [', ROOT_CAUSE)
        self.assertIn('const needsBenchmark = [', ROOT_CAUSE)
        self.assertIn('const needsIncidents = [', ROOT_CAUSE)
        self.assertIn(': Promise.resolve(null)', ROOT_CAUSE)

    def test_vehicle_detail_is_investigation_only(self):
        self.assertIn(
            "if (activeView !== 'vehicle-investigation')",
            ROOT_CAUSE,
        )

    def test_heavy_root_modules_are_lazy_mounted(self):
        mapping = {
            'cases': 'DiagnosticCaseIntelligence',
            'fleet-patterns': 'FleetPatternIntelligence',
            'prognostics': 'PrognosticMaintenanceIntelligence',
            'automation': 'OperationalAutomationIntelligence',
            'fleet-decisions': 'FleetDecisionIntelligence',
            'vehicle-twin': 'VehicleOperationalTwin',
            'planning': 'FleetIntelligencePlanning',
            'fleet-command': 'FleetCommandOperations',
            'transitions': 'DiagnosticTransitionIntelligence',
            'episodes': 'DiagnosticEpisodeIntelligence',
            'events': 'DiagnosticEventFeed',
            'replay': 'DiagnosticReplay',
        }
        for view, component in mapping.items():
            self.assertIn(f"activeView === '{view}'", ROOT_CAUSE)
            self.assertIn(f'<{component}', ROOT_CAUSE)

    def test_fleet_command_polls_active_workspace_only(self):
        self.assertIn(
            'async function refreshActiveWorkspace()',
            FLEET_COMMAND,
        )
        self.assertIn("if (workspace === 'COMMAND')", FLEET_COMMAND)
        self.assertIn("workspace === 'EXPLAINABILITY'", FLEET_COMMAND)
        self.assertIn("workspace === 'QUEUE'", FLEET_COMMAND)
        self.assertIn('  }, [runId, workspace]);', FLEET_COMMAND)
        self.assertNotIn('async function refreshAll()', FLEET_COMMAND)

    def test_explainability_detail_is_workspace_gated(self):
        self.assertIn(
            "if (workspace !== 'EXPLAINABILITY')",
            FLEET_COMMAND,
        )

    def test_page_tabs_are_controlled(self):
        self.assertIn('active: string;', TABS)
        self.assertIn('onChange: (view: string) => void;', TABS)
        self.assertNotIn('setMainView(', TABS)

    def test_root_css_no_nth_child_contract(self):
        root_part = CSS.split('Root Cause', 1)[1]
        self.assertNotIn('nth-of-type', root_part)
        self.assertIn('.diagnosticTopGrid', root_part)
        self.assertIn('.diagnosticWorkGrid', root_part)

    def test_no_pool_size_workaround(self):
        db = (ROOT / 'services/common/fleetmind_common/db.py').read_text()
        self.assertNotIn('pool_size=20', db)
        self.assertNotIn('max_overflow=30', db)


if __name__ == '__main__':
    unittest.main()
