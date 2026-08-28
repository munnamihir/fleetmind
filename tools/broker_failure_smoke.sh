#!/usr/bin/env bash
set -euo pipefail

OUTAGE_SECONDS="${OUTAGE_SECONDS:-5}"

echo "== FleetMind broker restart smoke test =="
echo "Restarting Redpanda to exercise client retry/recovery..."

docker compose restart redpanda
sleep "$OUTAGE_SECONDS"

docker compose ps

echo
echo "Worker recovery logs:"
docker compose logs worker --since=2m --tail=120

echo
echo "Simulator recovery logs:"
docker compose logs simulator --since=2m --tail=120

echo
echo "API health:"
curl -fsS http://localhost:8000/health
echo

echo "This is a smoke test, not a production DR certification."
