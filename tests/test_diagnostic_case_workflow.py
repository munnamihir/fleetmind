from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class DiagnosticCaseWorkflowContractTests(unittest.TestCase):
    def test_status_workflow_is_explicit(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_case_rules.py"
        ).read_text()

        for value in (
            "OPEN",
            "ACKNOWLEDGED",
            "INVESTIGATING",
            "MONITORING",
            "CLOSED",
        ):
            self.assertIn(f'"{value}"', source)

    def test_review_priority_is_explicitly_not_failure_risk(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_case_rules.py"
        ).read_text()

        self.assertIn("Review priority", source)
        self.assertIn("NOT calibrated", source)
        self.assertIn("NOT private failure truth", source)

    def test_activity_types_cover_operator_workflow(self):
        source = (
            ROOT
            / "services/common/fleetmind_common/diagnostic_case_rules.py"
        ).read_text()

        for activity in (
            "CASE_CREATED",
            "STATUS_CHANGED",
            "PRIORITY_CHANGED",
            "ASSIGNED",
            "NOTE_ADDED",
        ):
            self.assertIn(f'"{activity}"', source)

    def test_assignment_can_be_cleared_without_deleting_case(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()

        self.assertIn("clear_assignment", source)
        self.assertIn("target_assignment = None", source)
        self.assertIn("case.assigned_to = target_assignment", source)
        self.assertNotIn("delete(DiagnosticCase)", source)

    def test_notes_append_audit_activity(self):
        source = (ROOT / "services/api/app/diagnostics.py").read_text()

        notes = source.split(
            '@router.post("/cases/{case_id}/notes")',
            1,
        )[1].split(
            '@router.get("/summary")',
            1,
        )[0]
        self.assertIn("CASE_ACTIVITY_NOTE_ADDED", notes)
        self.assertIn("case.note_count += 1", notes)
        self.assertIn("db.add(activity)", notes)

    def test_materializer_never_overwrites_existing_workflow(self):
        source = (
            ROOT
            / "services/ml/app/diagnostic_case_materialize.py"
        ).read_text()

        self.assertIn("existing_episode_ids", source)
        self.assertIn("if episode.id in existing_episode_ids", source)
        self.assertIn("continue", source)


if __name__ == "__main__":
    unittest.main()
