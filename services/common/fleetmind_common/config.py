import os


def _database_url() -> str:
    value = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://fleetmind:fleetmind@localhost:5432/fleetmind",
    )
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://") :]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://") :]
    return value


DATABASE_URL = _database_url()
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
TELEMETRY_TOPIC = os.getenv("TELEMETRY_TOPIC", "vehicle.telemetry.v1")
FAILURE_TOPIC = os.getenv("FAILURE_TOPIC", "vehicle.failure-events.v1")
