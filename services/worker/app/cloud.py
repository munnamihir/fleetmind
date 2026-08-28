from __future__ import annotations

from confluent_kafka import Consumer as KafkaConsumer

from fleetmind_common.kafka import ensure_fleetmind_topics, kafka_client_config
from app import main as worker


def _consumer(config: dict):
    return KafkaConsumer(kafka_client_config(**config))


def main() -> None:
    ensure_fleetmind_topics()
    worker.Consumer = _consumer
    worker.main()


if __name__ == "__main__":
    main()
