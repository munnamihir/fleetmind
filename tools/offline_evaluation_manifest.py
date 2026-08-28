#!/usr/bin/env python3
"""Create a reproducible offline-evaluation request manifest.

The actual training/evaluation command remains the existing FleetMind diagnostic
pipeline. This manifest freezes the requested run/lineage/snapshot identities
so CI or a batch runner can execute it without silently changing inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lineage", required=True)
    parser.add_argument("--benchmark-sha256", required=True)
    parser.add_argument("--feature-schema-sha256", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument(
        "--output",
        default="offline-evaluation-request.json",
    )
    args = parser.parse_args()

    manifest = {
        "manifestVersion": "fm-offline-eval-9.4-v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "lineage": args.lineage,
        "benchmarkSnapshotSha256": args.benchmark_sha256,
        "featureSchemaSha256": args.feature_schema_sha256,
        "modelVersion": args.model_version,
        "claims": {
            "inputsFrozen": True,
            "evaluationExecuted": False,
        },
    }
    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
    )
    manifest["requestSha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    output = Path(args.output)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(output)


if __name__ == "__main__":
    main()
