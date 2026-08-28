# FleetMind Roadmap Completion Runbook

This delivery implements the software roadmap from Phase 8.2 through Phase 9.5
in one cohesive pass.

It intentionally separates:

- **implemented software capability**, which is testable from the repository;
- **environment-dependent validation**, such as sustained throughput, SLO
  attainment and production RPO/RTO.

## Phase 8.2 — observed outcomes

Endpoints:

```text
POST /api/v1/diagnostics/closed-loop/outcomes/evaluate
GET  /api/v1/diagnostics/closed-loop/outcomes/summary
GET  /api/v1/diagnostics/closed-loop/outcomes
GET  /api/v1/diagnostics/closed-loop/outcomes/{outcome_id}
```

Preview:

```bash
curl -sS -X POST \
  http://localhost:8000/api/v1/diagnostics/closed-loop/outcomes/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"actor":"operator","materialize":false}' | python3 -m json.tool
```

Persist/update observable outcome records:

```bash
curl -sS -X POST \
  http://localhost:8000/api/v1/diagnostics/closed-loop/outcomes/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"actor":"operator","materialize":true}' | python3 -m json.tool
```

Re-running materialization updates the same evaluator-version outcome record as
additional post-execution evidence appears.

## Phase 8.3 — effectiveness analytics

```bash
curl -sS \
  'http://localhost:8000/api/v1/diagnostics/closed-loop/effectiveness?cohort_dimension=recommendationType' \
  | python3 -m json.tool
```

Group distributions are withheld below the configured evidence gate.

## Phase 8.4 — policy replay

Bootstrap the default control and candidate policies:

```bash
curl -sS -X POST \
  'http://localhost:8000/api/v1/diagnostics/closed-loop/policies/bootstrap?actor=operator' \
  | python3 -m json.tool
```

List policies:

```bash
curl -sS \
  http://localhost:8000/api/v1/diagnostics/closed-loop/policies \
  | python3 -m json.tool
```

Replay one policy:

```bash
curl -sS -X POST \
  'http://localhost:8000/api/v1/diagnostics/closed-loop/policies/1/evaluate' \
  -H 'Content-Type: application/json' \
  -d '{"actor":"operator","persist":true}' \
  | python3 -m json.tool
```

The preferred replay source is a frozen Fleet Decision snapshot. If only
partial recommendation source snapshots exist, the evaluation is explicitly
marked non-frozen and promotion is blocked.

Policy promotion changes governance metadata only. It does not silently swap
the existing live recommendation generator.

## Phase 8.5 — shadow experiments

```bash
curl -sS -X POST \
  http://localhost:8000/api/v1/diagnostics/closed-loop/shadow-experiments \
  -H 'Content-Type: application/json' \
  -d '{
    "controlPolicyId":1,
    "candidatePolicyId":2,
    "actor":"operator",
    "persist":true
  }' | python3 -m json.tool
```

Control and candidate policies receive the same frozen input. No recommendation
or workflow writes occur.

## Phase 9 optional platform profile

Start the normal FleetMind stack first:

```bash
docker compose up -d --build
```

Start multi-asset ingestion, archive, Prometheus and Grafana:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.platform.yml \
  --profile platform \
  up -d --build
```

Additional endpoints/UI:

```text
GET  /metrics
GET  /api/v1/platform/status
GET  /api/v1/platform/slo
POST /api/v1/platform/model-registry
GET  /api/v1/platform/model-registry
POST /api/v1/platform/model-registry/{id}/promote
GET  /api/v1/platform/model-registry/{id}/drift
GET  /api/v1/platform/assets/plugins
GET  /api/v1/platform/assets/summary
GET  /api/v1/platform/assets/{asset_id}
```

Web UI:

```text
Root Cause → Fleet Command → Closed Loop → Outcomes
Root Cause → Platform
```

Platform services:

```text
Prometheus  http://localhost:9090
Grafana     http://localhost:3000
```

Default local Grafana credentials come from `.env` and should be changed outside
a disposable development environment.

## Phase 9.2 throughput harness

Broker-only target mode:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.platform.yml \
  --profile loadtest \
  run --rm load-generator
```

Or from a local Python environment with `confluent-kafka` installed:

```bash
python3 tools/kafka_load_generator.py \
  --brokers localhost:19092 \
  --topic vehicle.telemetry.v1 \
  --mode broker \
  --rate 100000 \
  --duration 30
```

The final JSON reports requested and measured delivered rate. Do not call the
platform "100K events/sec validated" unless the measured result and downstream
lag/latency behavior support it.

Backpressure/replay:

```bash
RATE=20000 DURATION=15 \
  tools/backpressure_replay_test.sh
```

Broker restart:

```bash
tools/broker_failure_smoke.sh
```

## Phase 9.2 archive

Inspect the archive manifest:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.platform.yml \
  --profile platform \
  exec archive \
  cat /archive/manifest.json
```

Parquet is always supported. Iceberg append requires a configured external
catalog and pre-created tables.

## Phase 9.3 deployment

Render:

```bash
helm template fleetmind \
  deploy/helm/fleetmind \
  -f deploy/helm/fleetmind/values-dev.yaml
```

Staging example:

```bash
helm upgrade --install fleetmind \
  deploy/helm/fleetmind \
  --namespace fleetmind \
  --create-namespace \
  -f deploy/helm/fleetmind/values-staging.yaml \
  --set database.existingSecret=fleetmind-database
```

Local database restore smoke test:

```bash
tools/disaster_recovery_smoke.sh
```

## Phase 9.4 model ops

Run the existing diagnostic model pipeline as a reproducible offline evaluation:

```bash
tools/run_offline_evaluation.sh
```

Verify a locked benchmark artifact:

```bash
python3 tools/verify_benchmark_artifact.py \
  /path/to/benchmark.json.gz \
  --expected-sha256 <sha256>
```

Model registration is explicit:

```bash
curl -sS -X POST \
  http://localhost:8000/api/v1/platform/model-registry \
  -H 'Content-Type: application/json' \
  -d '{
    "modelName":"diagnostic-xgboost",
    "version":"9.4.0",
    "lineage":"fm-diagnostic-6.1-exp-v1",
    "artifactUri":"/artifacts/model.bundle",
    "artifactSha256":"<64-char-sha256>",
    "featureSchemaSha256":"<64-char-sha256>",
    "benchmarkSnapshotSha256":"<64-char-sha256>",
    "benchmarkStatus":"qualified",
    "actor":"operator"
  }' | python3 -m json.tool
```

Promotion is blocked if artifact identity, schema compatibility, benchmark
identity or benchmark qualification is missing.

## Phase 9.5 multi-asset

The optional platform profile generates and ingests:

- robot actuator/gearbox telemetry;
- DC charger thermal/power telemetry;
- energy-system inverter/module telemetry.

Check:

```bash
curl -sS \
  http://localhost:8000/api/v1/platform/assets/summary \
  | python3 -m json.tool
```

These plugins produce transparent **operational attention** only. They do not
produce autonomous actuator commands or calibrated safety/failure probability.

## Validation suites

```bash
PYTHONPATH=services/common \
python3 -m unittest discover \
  -s tests \
  -p 'test_remaining_phase_rules.py' \
  -v

python3 -m unittest discover \
  -s tests \
  -p 'test_remaining_phase_contracts.py' \
  -v
```

Then run the pre-existing suite:

```bash
python3 -m unittest discover -s tests -v
```

If your complete diagnostic tests require explicit module paths, preserve the
same `PYTHONPATH` convention already used by the repository.
