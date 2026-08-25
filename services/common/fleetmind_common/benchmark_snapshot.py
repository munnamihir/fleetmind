from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .ml_features import FeatureExample


SNAPSHOT_FORMAT = "fleetmind-benchmark-v1"


def _record(example: FeatureExample) -> dict:
    return {
        "vehicleId": example.vehicle_id,
        "anchorTimestamp": example.anchor_timestamp.isoformat(),
        "anchorMileage": float(example.anchor_mileage),
        "label": int(example.label),
        "features": example.features,
        "milesToFailure": (
            float(example.miles_to_failure) if example.miles_to_failure is not None else None
        ),
    }


def _example(record: dict) -> FeatureExample:
    return FeatureExample(
        vehicle_id=str(record["vehicleId"]),
        anchor_timestamp=datetime.fromisoformat(str(record["anchorTimestamp"])),
        anchor_mileage=float(record["anchorMileage"]),
        label=int(record["label"]),
        features=dict(record["features"]),
        miles_to_failure=(
            float(record["milesToFailure"])
            if record.get("milesToFailure") is not None
            else None
        ),
    )


def feature_schema_hash(examples: Sequence[FeatureExample]) -> str:
    keys = sorted({key for example in examples for key in example.features})
    payload = json.dumps(keys, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def snapshot_payload(examples: Sequence[FeatureExample], metadata: dict) -> bytes:
    payload = {
        "format": SNAPSHOT_FORMAT,
        "metadata": metadata,
        "examples": [_record(example) for example in examples],
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def snapshot_digest(examples: Sequence[FeatureExample], metadata: dict) -> str:
    return hashlib.sha256(snapshot_payload(examples, metadata)).hexdigest()


def save_snapshot(
    examples: Sequence[FeatureExample],
    path: str | Path,
    metadata: dict,
) -> dict:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = snapshot_payload(examples, metadata)
    digest = hashlib.sha256(raw).hexdigest()
    with gzip.open(destination, "wb", compresslevel=6) as handle:
        handle.write(raw)
    return {
        "artifactPath": str(destination),
        "sha256": digest,
        "featureSchemaSha256": feature_schema_hash(examples),
        "examples": len(examples),
        "positives": sum(example.label for example in examples),
        "vehicles": len({example.vehicle_id for example in examples}),
        "failureVehicles": len(
            {example.vehicle_id for example in examples if example.label == 1}
        ),
    }


def load_snapshot(path: str | Path, *, expected_sha256: str | None = None) -> tuple[list[FeatureExample], dict]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Locked benchmark artifact is missing: {source}")
    with gzip.open(source, "rb") as handle:
        raw = handle.read()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(
            "Locked benchmark integrity check failed: "
            f"expected {expected_sha256}, observed {digest}"
        )
    payload = json.loads(raw.decode("utf-8"))
    if payload.get("format") != SNAPSHOT_FORMAT:
        raise ValueError(f"Unsupported benchmark snapshot format: {payload.get('format')}")
    examples = [_example(record) for record in payload.get("examples", [])]
    schema_hash = feature_schema_hash(examples)
    metadata = dict(payload.get("metadata") or {})
    return examples, {
        "sha256": digest,
        "featureSchemaSha256": schema_hash,
        "metadata": metadata,
    }
