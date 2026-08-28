from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import select

from fleetmind_common.db import Base, SessionLocal, engine, ensure_schema_compatibility
from fleetmind_common.models import Telemetry
from fleetmind_common.platform_store import AssetTelemetryRecord


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("fleetmind-archive")

ARCHIVE_DIR = Path(
    os.getenv(
        "FLEETMIND_ARCHIVE_DIR",
        "/archive",
    )
)
MANIFEST_PATH = Path(
    os.getenv(
        "FLEETMIND_ARCHIVE_MANIFEST",
        str(ARCHIVE_DIR / "manifest.json"),
    )
)
BATCH_SIZE = max(
    100,
    int(os.getenv("ARCHIVE_BATCH_SIZE", "5000")),
)
POLL_SECONDS = max(
    5.0,
    float(os.getenv("ARCHIVE_POLL_SECONDS", "30")),
)
RETENTION_DAYS = max(
    1,
    int(os.getenv("ARCHIVE_RETENTION_DAYS", "30")),
)
ICEBERG_CATALOG_URI = os.getenv(
    "ICEBERG_CATALOG_URI",
    "",
).strip()
ICEBERG_WAREHOUSE = os.getenv(
    "ICEBERG_WAREHOUSE",
    "",
).strip()
ICEBERG_NAMESPACE = os.getenv(
    "ICEBERG_NAMESPACE",
    "fleetmind",
).strip()


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


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {
            "version": 1,
            "telemetryWatermarkId": 0,
            "assetWatermarkId": 0,
            "files": [],
            "iceberg": {
                "configured": bool(ICEBERG_CATALOG_URI),
                "lastError": None,
            },
        }

    try:
        value = json.loads(
            MANIFEST_PATH.read_text()
        )
        if isinstance(value, dict):
            return value
    except Exception:
        log.exception(
            "failed to read archive manifest"
        )

    return {
        "version": 1,
        "telemetryWatermarkId": 0,
        "assetWatermarkId": 0,
        "files": [],
        "iceberg": {
            "configured": bool(ICEBERG_CATALOG_URI),
            "lastError": "manifest reset after parse failure",
        },
    }


def save_manifest(
    manifest: dict,
) -> None:
    MANIFEST_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temp = MANIFEST_PATH.with_suffix(
        ".tmp"
    )
    temp.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
    )
    temp.replace(MANIFEST_PATH)


def _telemetry_records(
    watermark: int,
) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(Telemetry)
            .where(Telemetry.id > watermark)
            .order_by(Telemetry.id)
            .limit(BATCH_SIZE)
        ).scalars().all()

    return [
        {
            "id": row.id,
            "timestamp": row.timestamp,
            "experiment_id": row.experiment_id,
            "vehicle_id": row.vehicle_id,
            "model": row.model,
            "factory": row.factory,
            "firmware": row.firmware,
            "pump_revision": row.pump_revision,
            "mileage": float(row.mileage),
            "ambient_temp_c": float(row.ambient_temp_c),
            "speed_mph": float(row.speed_mph),
            "soc_pct": float(row.soc_pct),
            "pack_voltage_v": float(row.pack_voltage_v),
            "pack_current_a": float(row.pack_current_a),
            "battery_temp_c": float(row.battery_temp_c),
            "cell_imbalance_v": float(row.cell_imbalance_v),
            "motor_temp_c": float(row.motor_temp_c),
            "inverter_temp_c": float(row.inverter_temp_c),
            "motor_rpm": float(row.motor_rpm),
            "coolant_temp_c": float(row.coolant_temp_c),
            "pump_rpm": float(row.pump_rpm),
            "pump_current_a": float(row.pump_current_a),
            "risk_score": float(row.risk_score),
            "status": row.status,
        }
        for row in rows
    ]


def _asset_records(
    watermark: int,
) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(AssetTelemetryRecord)
            .where(
                AssetTelemetryRecord.id
                > watermark
            )
            .order_by(
                AssetTelemetryRecord.id
            )
            .limit(BATCH_SIZE)
        ).scalars().all()

    return [
        {
            "id": row.id,
            "event_id": row.event_id,
            "timestamp": row.timestamp,
            "experiment_id": row.experiment_id,
            "asset_id": row.asset_id,
            "asset_type": row.asset_type,
            "model": row.model,
            "site": row.site,
            "firmware": row.firmware,
            "metrics_json": row.metrics_json,
            "attention_score": float(
                row.attention_score
            ),
            "status": row.status,
            "evidence_json": row.evidence_json,
        }
        for row in rows
    ]


def _partition_path(
    dataset: str,
    rows: list[dict],
) -> Path:
    timestamp = rows[-1]["timestamp"]
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(
            tzinfo=timezone.utc
        )

    experiment = (
        rows[-1].get("experiment_id")
        or "untagged"
    )
    safe_experiment = "".join(
        char
        if char.isalnum()
        or char in "-_."
        else "_"
        for char in str(experiment)
    )

    return (
        ARCHIVE_DIR
        / dataset
        / f"experiment_id={safe_experiment}"
        / f"date={timestamp.date().isoformat()}"
    )


def write_parquet(
    dataset: str,
    rows: list[dict],
) -> Path | None:
    if not rows:
        return None

    directory = _partition_path(
        dataset,
        rows,
    )
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    first_id = rows[0]["id"]
    last_id = rows[-1]["id"]
    path = directory / (
        f"part-{first_id:012d}-"
        f"{last_id:012d}.parquet"
    )

    table = pa.Table.from_pylist(rows)
    pq.write_table(
        table,
        path,
        compression="zstd",
    )
    return path


def append_iceberg(
    dataset: str,
    parquet_rows: list[dict],
) -> dict:
    if (
        not ICEBERG_CATALOG_URI
        or not parquet_rows
    ):
        return {
            "configured": False,
            "appended": False,
        }

    try:
        from pyiceberg.catalog import load_catalog

        properties = {
            "uri": ICEBERG_CATALOG_URI,
        }
        if ICEBERG_WAREHOUSE:
            properties["warehouse"] = (
                ICEBERG_WAREHOUSE
            )

        catalog = load_catalog(
            "fleetmind",
            **properties,
        )

        identifier = (
            ICEBERG_NAMESPACE,
            dataset,
        )

        table = catalog.load_table(
            identifier
        )
        arrow_table = pa.Table.from_pylist(
            parquet_rows
        )
        table.append(arrow_table)

        return {
            "configured": True,
            "appended": True,
            "table": ".".join(identifier),
        }
    except Exception as exc:
        log.warning(
            "Iceberg append unavailable dataset=%s: %s",
            dataset,
            exc,
        )
        return {
            "configured": True,
            "appended": False,
            "error": str(exc),
        }


def enforce_retention(
    manifest: dict,
) -> int:
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(
            days=RETENTION_DAYS
        )
    )
    removed = 0
    retained_files = []

    for record in (
        manifest.get("files")
        or []
    ):
        path = Path(
            str(record.get("path") or "")
        )
        created_raw = record.get(
            "createdAt"
        )
        try:
            created = (
                datetime.fromisoformat(
                    str(created_raw).replace(
                        "Z",
                        "+00:00",
                    )
                )
            )
        except (TypeError, ValueError):
            created = _utc_from_mtime(
                path
            )

        if (
            created is not None
            and created < cutoff
            and path.exists()
        ):
            try:
                path.unlink()
                removed += 1
                continue
            except OSError:
                log.exception(
                    "failed archive retention delete %s",
                    path,
                )

        retained_files.append(
            record
        )

    manifest["files"] = retained_files
    return removed


def _utc_from_mtime(
    path: Path,
) -> datetime | None:
    try:
        return datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=timezone.utc,
        )
    except OSError:
        return None


def archive_once(
    manifest: dict,
) -> int:
    written = 0

    telemetry_rows = _telemetry_records(
        int(
            manifest.get(
                "telemetryWatermarkId",
                0,
            )
            or 0
        )
    )
    if telemetry_rows:
        path = write_parquet(
            "telemetry",
            telemetry_rows,
        )
        if path is not None:
            manifest[
                "telemetryWatermarkId"
            ] = telemetry_rows[-1]["id"]
            manifest.setdefault(
                "files",
                [],
            ).append(
                {
                    "dataset": "telemetry",
                    "path": str(path),
                    "rows": len(
                        telemetry_rows
                    ),
                    "firstId": (
                        telemetry_rows[0][
                            "id"
                        ]
                    ),
                    "lastId": (
                        telemetry_rows[-1][
                            "id"
                        ]
                    ),
                    "createdAt": (
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                    ),
                }
            )
            manifest["iceberg"] = (
                append_iceberg(
                    "telemetry",
                    telemetry_rows,
                )
            )
            written += len(
                telemetry_rows
            )

    asset_rows = _asset_records(
        int(
            manifest.get(
                "assetWatermarkId",
                0,
            )
            or 0
        )
    )
    if asset_rows:
        path = write_parquet(
            "asset_telemetry",
            asset_rows,
        )
        if path is not None:
            manifest[
                "assetWatermarkId"
            ] = asset_rows[-1]["id"]
            manifest.setdefault(
                "files",
                [],
            ).append(
                {
                    "dataset": (
                        "asset_telemetry"
                    ),
                    "path": str(path),
                    "rows": len(asset_rows),
                    "firstId": (
                        asset_rows[0]["id"]
                    ),
                    "lastId": (
                        asset_rows[-1]["id"]
                    ),
                    "createdAt": (
                        datetime.now(
                            timezone.utc
                        ).isoformat()
                    ),
                }
            )
            manifest["icebergAssets"] = (
                append_iceberg(
                    "asset_telemetry",
                    asset_rows,
                )
            )
            written += len(asset_rows)

    manifest["retention"] = {
        "days": RETENTION_DAYS,
        "lastRemoved": (
            enforce_retention(
                manifest
            )
        ),
    }
    manifest["updatedAt"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )
    save_manifest(manifest)
    return written


def main() -> None:
    wait_for_db()
    ARCHIVE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest = load_manifest()
    log.info(
        "archive started dir=%s batch=%s poll=%.1fs retention=%sd iceberg=%s",
        ARCHIVE_DIR,
        BATCH_SIZE,
        POLL_SECONDS,
        RETENTION_DAYS,
        bool(ICEBERG_CATALOG_URI),
    )

    while True:
        try:
            written = archive_once(
                manifest
            )
            if written:
                log.info(
                    "archived rows=%s telemetry_watermark=%s asset_watermark=%s",
                    written,
                    manifest.get(
                        "telemetryWatermarkId"
                    ),
                    manifest.get(
                        "assetWatermarkId"
                    ),
                )
        except Exception:
            log.exception(
                "archive pass failed"
            )

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
