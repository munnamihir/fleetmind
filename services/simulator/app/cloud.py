from __future__ import annotations

from confluent_kafka import Producer as KafkaProducer

from fleetmind_common.kafka import ensure_fleetmind_topics, kafka_client_config
from app import main as simulator


def _producer(config: dict):
    return KafkaProducer(kafka_client_config(**config))


def main() -> None:
    ensure_fleetmind_topics()
    simulator.Producer = _producer
    simulator.main()


if __name__ == "__main__":
    main()
