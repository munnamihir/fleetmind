import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://fleetmind:fleetmind@localhost:5432/fleetmind",
)
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
TELEMETRY_TOPIC = os.getenv("TELEMETRY_TOPIC", "vehicle.telemetry.v1")
