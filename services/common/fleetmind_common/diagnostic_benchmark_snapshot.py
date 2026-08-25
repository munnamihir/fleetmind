from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .diagnostic_dataset import DiagnosticExample
from .diagnostics import diagnostic_feature_schema_hash


DIAGNOSTIC_SNAPSHOT_FORMAT = "fleetmind-diagnostic-benchmark-v1"


def _record(example: DiagnosticExample) -> dict:
    return {
        "vehicleId": example.vehicle_id,
        "experimentId": example.experiment_id,
        "anchorTimestamp": example.anchor_timestamp.isoformat(),
        "anchorMileage": float(example.anchor_mileage),
        "label": example.label,
        "features": example.features,
        "milesToFailure": (
            float(example.miles_to_failure)
            if example.miles_to_failure is not None
            else None
        ),
    }


def _example(record: dict) -> DiagnosticExample:
    return DiagnosticExample(
        vehicle_id=str(record["vehicleId"]),
        experiment_id=str(record["experimentId"]),
        anchor_timestamp=datetime.fromisoformat(
            str(record["anchorTimestamp"])
        ),
        anchor_mileage=float(record["anchorMileage"]),
        label=str(record["label"]),
        features={
            str(key): float(value)
            for key, value in dict(record["features"]).items()
        },
        miles_to_failure=(
            float(record["milesToFailure"])
            if record.get("milesToFailure") is not None
            else None
        ),
    )


def snapshot_payload(
    examples: Sequence[DiagnosticExample],
    metadata: dict,
) -> bytes:
    payload = {
        "format": DIAGNOSTIC_SNAPSHOT_FORMAT,
        "metadata": metadata,
        "examples": [_record(example) for example in examples],
    }
    return json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def snapshot_digest(
    examples: Sequence[DiagnosticExample],
    metadata: dict,
) -> str:
    return hashlib.sha256(
        snapshot_payload(examples, metadata)
    ).hexdigest()


def _schema_hash(examples: Sequence[DiagnosticExample]) -> str:
    if not examples:
        raise ValueError(
            "Cannot compute diagnostic benchmark schema from zero examples"
        )
    return diagnostic_feature_schema_hash(examples[0].features)


def save_snapshot_once(
    examples: Sequence[DiagnosticExample],
    path: str | Path,
    metadata: dict,
) -> dict:
    """Create an immutable diagnostic benchmark snapshot.

    Existing snapshots are never overwritten. The caller must load and verify
    an existing snapshot instead of regenerating it under the same
    lineage/experiment identity.
    """

    if not examples:
        raise ValueError("Cannot lock an empty diagnostic benchmark")

    experiment_ids = {
        example.experiment_id
        for example in examples
    }
    if len(experiment_ids) != 1:
        raise ValueError(
            "Diagnostic benchmark snapshot cannot mix experiments"
        )

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        raise FileExistsError(
            f"Diagnostic benchmark snapshot is already locked: {destination}"
        )

    raw = snapshot_payload(examples, metadata)
    digest = hashlib.sha256(raw).hexdigest()

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    os.close(fd)
    temporary_path = Path(temporary_name)

    try:
        with gzip.open(
            temporary_path,
            "wb",
            compresslevel=6,
        ) as handle:
            handle.write(raw)

        # Refuse to replace anything that appeared between the existence check
        # and the final move.
        if destination.exists():
            raise FileExistsError(
                f"Diagnostic benchmark snapshot was concurrently locked: "
                f"{destination}"
            )

        os.link(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)

    return {
        "artifactPath": str(destination),
        "sha256": digest,
        "featureSchemaSha256": _schema_hash(examples),
        "examples": len(examples),
        "vehicles": len(
            {example.vehicle_id for example in examples}
        ),
    }


def load_snapshot(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    expected_experiment_id: str | None = None,
    expected_lineage: str | None = None,
) -> tuple[list[DiagnosticExample], dict]:
    source = Path(path)

    if not source.exists():
        raise FileNotFoundError(
            f"Locked diagnostic benchmark artifact is missing: {source}"
        )

    with gzip.open(source, "rb") as handle:
        raw = handle.read()

    digest = hashlib.sha256(raw).hexdigest()

    if (
        expected_sha256 is not None
        and digest != expected_sha256
    ):
        raise ValueError(
            "Locked diagnostic benchmark integrity check failed: "
            f"expected {expected_sha256}, observed {digest}"
        )

    payload = json.loads(raw.decode("utf-8"))

    if payload.get("format") != DIAGNOSTIC_SNAPSHOT_FORMAT:
        raise ValueError(
            "Unsupported diagnostic benchmark snapshot format: "
            f"{payload.get('format')}"
        )

    metadata = dict(payload.get("metadata") or {})
    examples = [
        _example(record)
        for record in payload.get("examples", [])
    ]

    if not examples:
        raise ValueError(
            "Locked diagnostic benchmark contains no examples"
        )

    experiment_ids = {
        example.experiment_id
        for example in examples
    }
    if len(experiment_ids) != 1:
        raise ValueError(
            "Locked diagnostic benchmark mixes experiment IDs"
        )

    observed_experiment_id = next(iter(experiment_ids))

    if (
        expected_experiment_id is not None
        and observed_experiment_id != expected_experiment_id
    ):
        raise ValueError(
            "Locked diagnostic benchmark experiment mismatch: "
            f"expected {expected_experiment_id}, "
            f"observed {observed_experiment_id}"
        )

    if (
        expected_lineage is not None
        and metadata.get("lineage") != expected_lineage
    ):
        raise ValueError(
            "Locked diagnostic benchmark lineage mismatch: "
            f"expected {expected_lineage}, "
            f"observed {metadata.get('lineage')}"
        )

    return examples, {
        "sha256": digest,
        "featureSchemaSha256": _schema_hash(examples),
        "metadata": metadata,
        "examples": len(examples),
        "vehicles": len(
            {example.vehicle_id for example in examples}
        ),
    }
