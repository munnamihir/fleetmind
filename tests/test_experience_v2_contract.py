from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'web' / 'src' / 'main.tsx').read_text()
V2 = (ROOT / 'web' / 'src' / 'FleetMindExperienceV2.tsx').read_text()
CSS = (ROOT / 'web' / 'src' / 'FleetMindExperienceV2.css').read_text()
RESPONSIVE = (ROOT / 'web' / 'src' / 'FleetMindExperienceV2Responsive.css').read_text()
WORK_INBOX = (ROOT / 'web' / 'src' / 'FleetMindWorkInbox.tsx').read_text()
DOCKERFILE = (ROOT / 'web' / 'Dockerfile').read_text()
DOCKERIGNORE = (ROOT / 'web' / '.dockerignore').read_text()


class FleetMindExperienceV2ContractTests(unittest.TestCase):
    def test_v2_shell_is_mounted(self):
        self.assertIn("import { FleetMindExperienceV2 }", MAIN)
        self.assertIn('<FleetMindExperienceV2 />', MAIN)

    def test_command_bar_reuses_existing_search_and_help(self):
        self.assertIn("trigger('.fmExperienceSearchButton')", V2)
        self.assertIn("trigger('.fmExperienceGuideButton')", V2)
        self.assertIn("trigger('.fmWorkInboxLauncher')", V2)

    def test_command_bar_has_keyboard_first_access(self):
        self.assertIn("event.metaKey || event.ctrlKey", V2)
        self.assertIn("event.key.toLowerCase() === 'k'", V2)
        self.assertIn("event.shiftKey && event.key.toLowerCase() === 'w'", V2)
        self.assertIn("event.shiftKey && event.key.toLowerCase() === 'f'", V2)

    def test_api_status_is_read_only(self):
        self.assertIn("fetch(`${API}/health`", V2)
        self.assertNotIn("method: 'POST'", V2)
        self.assertNotIn('method: "POST"', V2)

    def test_density_and_focus_are_persistent_ui_preferences(self):
        self.assertIn("fleetmind-density", V2)
        self.assertIn("dataset.fmDensity", V2)
        self.assertIn("dataset.fmFocus", V2)
        self.assertIn("data-fm-density='compact'", CSS)
        self.assertIn("data-fm-focus='true'", CSS)

    def test_mobile_navigation_is_present(self):
        self.assertIn('fmV2MobileNav', V2)
        self.assertIn('@media (max-width: 650px)', CSS)
        self.assertIn('grid-template-columns: repeat(5, 1fr)', CSS)

    def test_accessibility_and_reduced_motion_are_preserved(self):
        self.assertIn('aria-label="FleetMind command bar"', V2)
        self.assertIn('aria-pressed={focusMode}', V2)
        self.assertIn('@media (prefers-reduced-motion: reduce)', CSS)

    def test_focus_mode_removes_hidden_legacy_sidebar_from_grid_flow(self):
        self.assertIn("html[data-fm-focus='true'] .shell > .sidebar", RESPONSIVE)
        self.assertIn('display: none !important', RESPONSIVE)

    def test_my_work_outcomes_are_pinned_to_resolved_run(self):
        self.assertIn('runId: number', WORK_INBOX)
        self.assertIn('outcomes/summary?run_id=', WORK_INBOX)
        self.assertIn('String(nextCommand.runId)', WORK_INBOX)

    def test_web_container_uses_platform_correct_dependencies(self):
        self.assertIn('COPY package.json ./', DOCKERFILE)
        self.assertIn('npm install --include=optional', DOCKERFILE)
        self.assertIn('node_modules', DOCKERIGNORE)
        self.assertIn('package-lock.json', DOCKERIGNORE)

    def test_v2_does_not_introduce_autonomous_workflow_language(self):
        lowered = V2.lower()
        self.assertNotIn('auto-approve', lowered)
        self.assertNotIn('auto execute', lowered)
        self.assertNotIn('autonomous repair', lowered)


if __name__ == '__main__':
    unittest.main()
