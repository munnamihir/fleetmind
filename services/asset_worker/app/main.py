from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime

from confluent_kafka import Consumer, KafkaError
from sqlalchemy import select

from fleetmind_common.asset_plugins import score_asset_event, validate_asset_event
from fleetmind_common.db import Base, SessionLocal, engine, ensure_schema_compatibility
from fleetmind_common.platform_store import AssetTelemetryRecord

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("fleetmind-asset-worker")

KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "redpanda:9092",
)
ASSET_TELEMETRY_TOPIC = os.getenv(
    "ASSET_TELEMETRY_TOPIC",
    "asset.telemetry.v1",
)
BATCH_SIZE = max(1, int(os.getenv("ASSET_WORKER_BATCH_SIZE", "250")))
BATCH_TIMEOUT = max(
    0.05,
    float(os.getenv("ASSET_WORKER_BATCH_TIMEOUT_SECONDS", "1.0")),
)
STATS_INTERVAL = max(
    5.0,
    float(os.getenv("ASSET_WORKER_STATS_INTERVAL_SECONDS", "15")),
)


def wait_for_db() -> None:
    for attempt in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            ensure_schema_compatibility()
            return
        except Exception as exc:
            log.warning(
                "database not ready (%s/30): %s",
                attempt + 1,
                exc,
            )
            time.sleep(2)
    raise RuntimeError("database unavailable")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def _row_from_event(
    event: dict,
) -> AssetTelemetryRecord:
    validation = validate_asset_event(event)
    if not validation["valid"]:
        raise ValueError(
            "; ".join(validation["errors"])
        )

    score = score_asset_event(event)
    context = (
        event.get("context")
        if isinstance(event.get("context"), dict)
        else {}
    )

    return AssetTelemetryRecord(
        event_id=str(event["eventId"]),
        timestamp=_parse_timestamp(
            str(event["timestamp"])
        ),
        experiment_id=str(
            event["experimentId"]
        ),
        asset_id=str(event["assetId"]),
        asset_type=str(event["assetType"]),
        model=(
            str(context.get("model"))
            if context.get("model") is not None
            else None
        ),
        site=(
            str(context.get("site"))
            if context.get("site") is not None
            else None
        ),
        firmware=(
            str(context.get("firmware"))
            if context.get("firmware") is not None
            else None
        ),
        metrics_json=json.dumps(
            event["metrics"],
            sort_keys=True,
        ),
        attention_score=float(
            score["attentionScore"]
        ),
        status=str(score["status"]),
        evidence_json=json.dumps(
            score["evidence"],
            sort_keys=True,
        ),
    )


def persist_batch(
    events: list[dict],
) -> int:
    if not events:
        return 0

    rows = []
    for event in events:
        try:
            rows.append(_row_from_event(event))
        except Exception:
            log.exception(
                "invalid asset event id=%s asset=%s",
                event.get("eventId"),
                event.get("assetId"),
            )

    if not rows:
        return 0

    event_ids = [
        row.event_id for row in rows
    ]

    with SessionLocal() as db:
        existing = set(
            db.execute(
                select(
                    AssetTelemetryRecord.event_id
                ).where(
                    AssetTelemetryRecord.event_id.in_(
                        event_ids
                    )
                )
            ).scalars().all()
        )

        unique_rows = [
            row
            for row in rows
            if row.event_id not in existing
        ]

        if not unique_rows:
            return 0

        db.add_all(unique_rows)
        db.commit()

    return len(unique_rows)


def main() -> None:
    wait_for_db()

    consumer = Consumer(
        {
            "bootstrap.servers": (
                KAFKA_BOOTSTRAP_SERVERS
            ),
            "group.id": (
                "fleetmind-multi-asset-worker-v1"
            ),
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )
    consumer.subscribe(
        [ASSET_TELEMETRY_TOPIC]
    )

    log.info(
        "consuming asset telemetry=%s from %s batch=%s",
        ASSET_TELEMETRY_TOPIC,
        KAFKA_BOOTSTRAP_SERVERS,
        BATCH_SIZE,
    )

    processed = 0
    last_stats = time.time()

    try:
        while True:
            messages = consumer.consume(
                num_messages=BATCH_SIZE,
                timeout=BATCH_TIMEOUT,
            )

            if not messages:
                continue

            events: list[dict] = []
            for message in messages:
                if message is None:
                    continue

                if message.error():
                    if (
                        message.error().code()
                        != KafkaError._PARTITION_EOF
                    ):
                        log.error(
                            "kafka error: %s",
                            message.error(),
                        )
                    continue

                try:
                    events.append(
                        json.loads(
                            message.value().decode(
                                "utf-8"
                            )
                        )
                    )
                except Exception:
                    log.exception(
                        "failed to decode asset telemetry"
                    )

            try:
                processed += persist_batch(
                    events
                )
            except Exception:
                log.exception(
                    "asset batch persistence failed size=%s",
                    len(events),
                )

            now = time.time()
            if (
                now - last_stats
                >= STATS_INTERVAL
            ):
                log.info(
                    "asset worker throughput rows=%s",
                    processed,
                )
                processed = 0
                last_stats = now
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
