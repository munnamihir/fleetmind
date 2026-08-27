import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "web" / "src" / "FleetCommandOperations.tsx"
CSS = ROOT / "web" / "src" / "FleetCommandOperations.css"


class FleetCommandNestedTabsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = UI.read_text()
        cls.css = CSS.read_text()

    def test_four_secondary_tab_bars_exist(self):
        for label in (
            'ariaLabel="Command Center views"',
            'ariaLabel="Explainability views"',
            'ariaLabel="Decision Queue views"',
            'ariaLabel="Closed Loop views"',
        ):
            self.assertIn(label, self.ui)

    def test_command_center_sections_are_tabbed(self):
        for label in (
            "Overview",
            "Operator Queues",
            "Cohorts",
            "Attention Factors",
        ):
            self.assertIn(label, self.ui)

    def test_explainability_sections_are_tabbed(self):
        for label in (
            "Attention",
            "Evidence",
            "Lineage",
        ):
            self.assertIn(label, self.ui)

    def test_queue_sections_are_tabbed(self):
        for label in (
            "Active Queue",
            "Ownership",
            "Workflow Status",
        ):
            self.assertIn(label, self.ui)

    def test_closed_loop_sections_are_tabbed(self):
        for label in (
            "Evaluate",
            "Evaluation Results",
            "Recommendations",
            "Lifecycle",
        ):
            self.assertIn(label, self.ui)

    def test_materialization_remains_selected_vehicle_only(self):
        self.assertIn(
            "materialize\n                ? [selectedVehicleId]\n                : null",
            self.ui,
        )

    def test_human_gate_and_truth_boundary_remain_visible(self):
        self.assertIn(
            "queue priority ≠ physical risk",
            self.ui,
        )
        self.assertIn(
            "execution ≠ physical repair",
            self.ui,
        )
        self.assertIn(
            "Human control remains mandatory.",
            self.ui,
        )
        self.assertIn(
            "EXECUTION READY → EXECUTED",
            self.ui,
        )

    def test_nested_tabs_have_distinct_styling(self):
        self.assertIn(".fleetOpsSubTabs", self.css)
        self.assertIn(".fleetOpsSubTab.active", self.css)
        self.assertIn(".fleetOpsSubTabPanel", self.css)

    def test_nested_tabs_have_responsive_rules(self):
        self.assertIn("@media (max-width: 1050px)", self.css)
        self.assertIn("@media (max-width: 800px)", self.css)
        self.assertIn("@media (max-width: 570px)", self.css)


if __name__ == "__main__":
    unittest.main()
