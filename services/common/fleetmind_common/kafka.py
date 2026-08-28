from __future__ import annotations

import os
from typing import Any

from confluent_kafka.admin import AdminClient, NewTopic

from .config import FAILURE_TOPIC, KAFKA_BOOTSTRAP_SERVERS, TELEMETRY_TOPIC


def kafka_client_config(**overrides: Any) -> dict[str, Any]:
    """Build a confluent-kafka configuration for local or managed Kafka.

    Local development remains PLAINTEXT by default. Managed providers such as
    Redpanda Cloud can be enabled entirely with environment variables without
    changing application code.
    """

    config: dict[str, Any] = {
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
    }

    security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT").strip()
    if security_protocol:
        config["security.protocol"] = security_protocol

    username = os.getenv("KAFKA_SASL_USERNAME", "").strip()
    password = os.getenv("KAFKA_SASL_PASSWORD", "")
    mechanism = os.getenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-256").strip()

    if username or password:
        config.update(
            {
                "security.protocol": security_protocol or "SASL_SSL",
                "sasl.mechanism": mechanism,
                "sasl.username": username,
                "sasl.password": password,
            }
        )

    ssl_ca_location = os.getenv("KAFKA_SSL_CA_LOCATION", "").strip()
    if ssl_ca_location:
        config["ssl.ca.location"] = ssl_ca_location

    config.update(overrides)
    return config


def ensure_fleetmind_topics() -> None:
    """Create FleetMind topics when the broker account is allowed to do so.

    Set KAFKA_AUTO_CREATE_TOPICS=false when topics are managed separately.
    Existing topics are never modified.
    """

    enabled = os.getenv("KAFKA_AUTO_CREATE_TOPICS", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return

    partitions = max(1, int(os.getenv("KAFKA_TOPIC_PARTITIONS", "3")))
    replication_factor = max(1, int(os.getenv("KAFKA_TOPIC_REPLICATION_FACTOR", "3")))

    admin = AdminClient(kafka_client_config())
    metadata = admin.list_topics(timeout=15)
    existing = set(metadata.topics)

    missing = [
        NewTopic(topic, num_partitions=partitions, replication_factor=replication_factor)
        for topic in (TELEMETRY_TOPIC, FAILURE_TOPIC)
        if topic not in existing
    ]
    if not missing:
        return

    futures = admin.create_topics(missing)
    for topic, future in futures.items():
        try:
            future.result(timeout=20)
        except TypeError:
            # Older confluent-kafka Future.result implementations do not accept
            # a timeout. The admin operation itself still has bounded broker IO.
            future.result()
        except Exception as exc:  # pragma: no cover - provider-specific errors
            message = str(exc).lower()
            if "already exists" not in message:
                raise RuntimeError(f"unable to create Kafka topic {topic}: {exc}") from exc
