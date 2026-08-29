from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RENDER = (ROOT / "render.yaml").read_text()
CONFIG = (ROOT / "services" / "common" / "fleetmind_common" / "config.py").read_text()
KAFKA = (ROOT / "services" / "common" / "fleetmind_common" / "kafka.py").read_text()
WORKER_CLOUD = (ROOT / "services" / "worker" / "app" / "cloud.py").read_text()
SIMULATOR_CLOUD = (ROOT / "services" / "simulator" / "app" / "cloud.py").read_text()


class CloudRuntimeContractTests(unittest.TestCase):
    def test_render_blueprint_uses_only_free_public_services(self):
        self.assertNotIn("runtime: docker", RENDER)
        self.assertNotIn("dockerfilePath", RENDER)
        self.assertIn("runtime: static", RENDER)
        self.assertIn("runtime: python", RENDER)
        self.assertIn("plan: free", RENDER)
        self.assertNotIn("type: worker", RENDER)
        self.assertNotIn("disk:", RENDER)
        self.assertNotIn("databases:", RENDER)

    def test_public_console_has_same_origin_api_proxy(self):
        self.assertIn("source: /api/*", RENDER)
        self.assertIn("source: /health", RENDER)
        self.assertIn("VITE_API_URL= npm run build", RENDER)
        self.assertIn("destination: /index.html", RENDER)

    def test_external_free_postgres_is_secret_driven(self):
        self.assertIn("- key: DATABASE_URL\n        sync: false", RENDER)
        self.assertNotIn("fromDatabase:", RENDER)
        self.assertIn('value.startswith("postgresql://")', CONFIG)
        self.assertIn("postgresql+psycopg://", CONFIG)

    def test_paid_streaming_services_are_not_provisioned(self):
        self.assertNotIn("fleetmind-worker-munnamihir", RENDER)
        self.assertNotIn("fleetmind-simulator-munnamihir", RENDER)
        self.assertNotIn("fleetmind-ml-munnamihir", RENDER)
        self.assertNotIn("KAFKA_BOOTSTRAP_SERVERS", RENDER)
        self.assertNotIn("KAFKA_SASL_PASSWORD", RENDER)

    def test_streaming_runtime_remains_available_in_source(self):
        self.assertIn('"security.protocol"', KAFKA)
        self.assertIn('"sasl.mechanism"', KAFKA)
        self.assertIn("worker.main()", WORKER_CLOUD)
        self.assertIn("simulator.main()", SIMULATOR_CLOUD)
        self.assertIn("ensure_fleetmind_topics", WORKER_CLOUD)
        self.assertIn("ensure_fleetmind_topics", SIMULATOR_CLOUD)

    def test_public_demo_mode_is_explicit(self):
        self.assertIn("FLEETMIND_PUBLIC_DEMO", RENDER)
        self.assertIn('value: "true"', RENDER)


if __name__ == "__main__":
    unittest.main()
