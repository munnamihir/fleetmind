from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RENDER = (ROOT / "render.yaml").read_text()
CONFIG = (ROOT / "services" / "common" / "fleetmind_common" / "config.py").read_text()
KAFKA = (ROOT / "services" / "common" / "fleetmind_common" / "kafka.py").read_text()
WORKER_CLOUD = (ROOT / "services" / "worker" / "app" / "cloud.py").read_text()
SIMULATOR_CLOUD = (ROOT / "services" / "simulator" / "app" / "cloud.py").read_text()


class CloudRuntimeContractTests(unittest.TestCase):
    def test_render_blueprint_uses_no_docker_runtime(self):
        self.assertNotIn("runtime: docker", RENDER)
        self.assertNotIn("dockerfilePath", RENDER)
        self.assertIn("runtime: static", RENDER)
        self.assertIn("runtime: python", RENDER)

    def test_public_console_has_same_origin_api_proxy(self):
        self.assertIn("source: /api/*", RENDER)
        self.assertIn("source: /health", RENDER)
        self.assertIn("VITE_API_URL= npm run build", RENDER)
        self.assertIn("destination: /index.html", RENDER)

    def test_postgres_is_managed_and_private(self):
        self.assertIn("fromDatabase:", RENDER)
        self.assertIn("property: connectionString", RENDER)
        self.assertIn("ipAllowList: []", RENDER)
        self.assertIn('value.startswith("postgresql://")', CONFIG)
        self.assertIn("postgresql+psycopg://", CONFIG)

    def test_managed_kafka_supports_tls_and_sasl(self):
        self.assertIn('"security.protocol"', KAFKA)
        self.assertIn('"sasl.mechanism"', KAFKA)
        self.assertIn('"sasl.username"', KAFKA)
        self.assertIn('"sasl.password"', KAFKA)
        self.assertIn("SASL_SSL", RENDER)
        self.assertIn("SCRAM-SHA-256", RENDER)

    def test_kafka_secrets_are_not_committed(self):
        self.assertIn("KAFKA_SASL_PASSWORD\n        sync: false", RENDER)
        self.assertIn("KAFKA_SASL_USERNAME\n        sync: false", RENDER)
        self.assertNotIn("sasl.password:\n", RENDER)

    def test_cloud_workers_reuse_existing_business_logic(self):
        self.assertIn("worker.main()", WORKER_CLOUD)
        self.assertIn("simulator.main()", SIMULATOR_CLOUD)
        self.assertIn("kafka_client_config", WORKER_CLOUD)
        self.assertIn("kafka_client_config", SIMULATOR_CLOUD)
        self.assertIn("ensure_fleetmind_topics", WORKER_CLOUD)
        self.assertIn("ensure_fleetmind_topics", SIMULATOR_CLOUD)

    def test_ml_artifacts_are_persistent(self):
        self.assertIn("mountPath: /var/data/fleetmind-artifacts", RENDER)
        self.assertIn("ML_ARTIFACT_DIR", RENDER)


if __name__ == "__main__":
    unittest.main()
