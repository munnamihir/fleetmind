import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODELS_FILE = ROOT / "services" / "common" / "fleetmind_common" / "models.py"


class ExperimentIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MODELS_FILE.read_text()

    def test_telemetry_schema_has_experiment_identity(self):
        telemetry_section = (
            self.source
            .split("class Telemetry(Base):", 1)[1]
            .split("class Alert(Base):", 1)[0]
        )

        self.assertIn("experiment_id:", telemetry_section)
        self.assertIn('mapped_column(String(64), nullable=True, index=True)', telemetry_section)

    def test_failure_truth_schema_has_experiment_identity(self):
        failure_section = (
            self.source
            .split("class FailureEvent(Base):", 1)[1]
            .split("class MLModelRun(Base):", 1)[0]
        )

        self.assertIn("experiment_id:", failure_section)
        self.assertIn('mapped_column(String(64), nullable=True, index=True)', failure_section)


if __name__ == "__main__":
    unittest.main()
