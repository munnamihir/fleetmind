#!/usr/bin/env bash
set -euo pipefail

RATE="${RATE:-20000}"
DURATION="${DURATION:-15}"
TOPIC="${TELEMETRY_TOPIC:-vehicle.telemetry.v1}"

echo "== FleetMind backpressure/replay smoke test =="
echo "Stopping worker so Kafka accumulates a replayable backlog..."
docker compose stop worker

cleanup() {
  docker compose start worker >/dev/null 2>&1 || true
}
trap cleanup EXIT

python3 tools/kafka_load_generator.py \
  --brokers localhost:19092 \
  --topic "$TOPIC" \
  --mode vehicle \
  --rate "$RATE" \
  --duration "$DURATION"

echo
echo "Consumer group lag while worker is stopped:"
docker compose exec -T redpanda \
  rpk group describe fleetmind-reliability-worker-v2 \
  --brokers redpanda:9092 || true

echo
echo "Restarting worker..."
docker compose start worker
trap - EXIT

echo "Waiting briefly for replay..."
sleep 10

echo
echo "Consumer group after restart:"
docker compose exec -T redpanda \
  rpk group describe fleetmind-reliability-worker-v2 \
  --brokers redpanda:9092 || true

echo
echo "Recent worker logs:"
docker compose logs worker --since=2m --tail=100

echo
echo "This script exercises backlog/replay behavior; inspect lag convergence and errors."
