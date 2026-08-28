#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-artifacts/offline-evaluation}"
mkdir -p "$OUTPUT_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT="$OUTPUT_DIR/diagnostic-evaluation-$STAMP.json"

echo "== FleetMind reproducible offline diagnostic evaluation =="
echo "The diagnostic runner reuses the exact locked benchmark snapshot when present."

docker compose run --rm \
  ml-trainer \
  python -m app.diagnostic_run \
  > "$REPORT"

python3 - "$REPORT" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
report = json.loads(path.read_text())

print("status:", report.get("status"))
print("lineage:", report.get("lineage"))
print("experiment:", report.get("experimentId"))
print(
    "benchmark snapshot:",
    (report.get("benchmarkSnapshot") or {}).get("status"),
)
print(
    "benchmark sha256:",
    (report.get("benchmarkSnapshot") or {}).get("sha256"),
)
print(
    "feature schema:",
    report.get("featureSchemaSha256")
    or (report.get("benchmarkSnapshot") or {}).get("featureSchemaSha256"),
)
print("report:", path)

if (report.get("benchmarkSnapshot") or {}).get("status") != "locked":
    print(
        "NOTE: benchmark is not locked yet, so this run is not a frozen "
        "benchmark claim.",
        file=sys.stderr,
    )
PY
