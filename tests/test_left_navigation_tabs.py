from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
APP = ROOT / "web/src/App.tsx"


class LeftNavigationTabsContractTests(unittest.TestCase):
    def test_page_type_includes_new_tabs(self):
        source = APP.read_text()
        self.assertIn("'incidents'", source)
        self.assertIn("'cohorts'", source)
        self.assertIn("'components'", source)

    def test_left_nav_tabs_are_interactive_and_active(self):
        source = APP.read_text()
        for page in ("incidents", "cohorts", "components"):
            self.assertIn(
                f"className={{page === '{page}' ? 'navActive' : ''}}",
                source,
            )
            self.assertIn(
                f"onClick={{() => setPage('{page}')}}",
                source,
            )

    def test_each_tab_has_a_dedicated_dashboard(self):
        source = APP.read_text()
        self.assertIn("function IncidentsDashboard(", source)
        self.assertIn("function CohortsDashboard(", source)
        self.assertIn("function ComponentsDashboard(", source)
        self.assertIn("<IncidentsDashboard", source)
        self.assertIn("<CohortsDashboard", source)
        self.assertIn("<ComponentsDashboard", source)

    def test_tabs_reuse_existing_loaded_data(self):
        source = APP.read_text()
        self.assertNotIn("/api/v1/incidents", source)
        self.assertNotIn("/api/v1/components", source)
        self.assertIn("alerts={alerts}", source)
        self.assertIn("cohorts={cohorts}", source)
        self.assertIn("reliability={reliability}", source)

    def test_component_and_cohort_copy_remains_noncausal(self):
        source = APP.read_text()
        self.assertIn(
            "They do not by themselves establish component causality.",
            source,
        )
        self.assertIn(
            "telemetry signal proves physical causation",
            source,
        )


if __name__ == "__main__":
    unittest.main()
