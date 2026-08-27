import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'web/src/App.tsx'
TABS = ROOT / 'web/src/DashboardPageTabs.tsx'
CSS = ROOT / 'web/src/DashboardPageTabs.css'
ROOT_CAUSE = ROOT / 'web/src/RootCauseDashboard.tsx'


class DashboardPageTabsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = APP.read_text()
        cls.tabs = TABS.read_text()
        cls.css = CSS.read_text()
        cls.root_cause = ROOT_CAUSE.read_text()

    def test_app_mounts_controlled_page_tabs(self):
        self.assertIn('DashboardPageTabs,', self.app)
        self.assertIn('DEFAULT_DASHBOARD_VIEW', self.app)
        self.assertIn('data-dashboard-page={page}', self.app)
        self.assertIn('data-dashboard-view={activeDashboardView}', self.app)
        self.assertIn('active={activeDashboardView}', self.app)

    def test_all_left_navigation_pages_are_configured(self):
        for page in (
            'fleet',
            'incidents',
            'reliability',
            'cohorts',
            'components',
            'firmware',
            'ml',
            'diagnostics',
        ):
            self.assertIn(f'  {page}: [', self.tabs)

    def test_reliability_sections_are_tabs(self):
        for label in (
            'Survival Analysis',
            'Engineering Interpretation',
            'Cohort Scorecard',
            'Early Warning',
            'Failure Evaluation',
        ):
            self.assertIn(label, self.tabs)

    def test_firmware_sections_are_tabs(self):
        for label in (
            'Matched Cohort',
            'Hardware × Software',
            'Firmware Scorecard',
            'Method',
            'Interaction Matrix',
        ):
            self.assertIn(label, self.tabs)

    def test_ml_sections_are_tabs(self):
        for label in (
            'Benchmark',
            'Claim Policy',
            'Model Selection',
            'Confusion Matrix',
            'Explainability',
            'Calibration',
            'Risk History',
            'Predictions',
        ):
            self.assertIn(label, self.tabs)

    def test_root_cause_major_components_are_tabs(self):
        for label in (
            'Cases',
            'Fleet Patterns',
            'Prognostics',
            'Automation',
            'Fleet Decisions',
            'Vehicle Twin',
            'Planning',
            'Fleet Command',
            'Transitions',
            'Episodes',
            'Events',
            'Replay',
            'Model Comparison',
        ):
            self.assertIn(label, self.tabs)

    def test_heavy_root_components_are_lazy_mounted(self):
        for view in (
            'cases',
            'fleet-patterns',
            'prognostics',
            'automation',
            'fleet-decisions',
            'vehicle-twin',
            'planning',
            'fleet-command',
            'transitions',
            'episodes',
            'events',
            'replay',
        ):
            self.assertIn(
                f"activeView === '{view}'",
                self.root_cause,
            )

    def test_tab_strip_is_horizontal_and_scrollable(self):
        self.assertIn('overflow-x: auto', self.css)
        self.assertIn('white-space: nowrap', self.css)

    def test_root_css_uses_classes_not_child_order(self):
        root_part = self.css.split('Root Cause', 1)[1]
        self.assertNotIn('nth-of-type', root_part)
        self.assertIn('.diagnosticTopGrid', root_part)
        self.assertIn('.diagnosticWorkGrid', root_part)

    def test_css_covers_each_dashboard_family(self):
        for page in (
            "'fleet'",
            "'incidents'",
            "'reliability'",
            "'cohorts'",
            "'components'",
            "'firmware'",
            "'ml'",
            "'diagnostics'",
        ):
            self.assertIn(
                f'data-dashboard-page={page}',
                self.css,
            )


if __name__ == '__main__':
    unittest.main()
