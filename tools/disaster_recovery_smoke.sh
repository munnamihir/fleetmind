#!/usr/bin/env bash
set -euo pipefail

DB="${POSTGRES_DB:-fleetmind}"
USER="${POSTGRES_USER:-fleetmind}"
TEST_DB="fleetmind_dr_verify_$$"
BACKUP="/tmp/fleetmind-dr-$$_backup.dump"

cleanup() {
  docker compose exec -T postgres \
    dropdb -U "$USER" --if-exists "$TEST_DB" >/dev/null 2>&1 || true
  docker compose exec -T postgres \
    rm -f "$BACKUP" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== FleetMind PostgreSQL backup/restore smoke test =="

docker compose exec -T postgres \
  pg_dump -U "$USER" -d "$DB" -Fc -f "$BACKUP"

docker compose exec -T postgres \
  createdb -U "$USER" "$TEST_DB"

docker compose exec -T postgres \
  pg_restore -U "$USER" -d "$TEST_DB" "$BACKUP"

echo
echo "Verification counts from restored database:"
docker compose exec -T postgres \
  psql -U "$USER" -d "$TEST_DB" -Atc \
  "SELECT 'telemetry=' || count(*) FROM telemetry;
   SELECT 'diagnostic_runs=' || count(*) FROM diagnostic_model_runs;
   SELECT 'recommendations=' || count(*) FROM diagnostic_operational_recommendations;"

echo
echo "Restore smoke test completed. This validates the local procedure only."
