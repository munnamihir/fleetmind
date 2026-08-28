# FleetMind Cloud Runtime

FleetMind can run as an internet-accessible application without Docker Desktop or any localhost-only service.

## Target architecture

```text
Browser / phone / tablet
        |
        v
Render Static Site (FleetMind console)
        |  same-origin rewrite: /api/* and /health
        v
Render FastAPI Web Service
        |
        +----------------------+
        |                      |
        v                      v
Render Postgres          Render background workers
                               |
                               +-- ingestion worker
                               +-- simulator
                               +-- ML trainer + persistent artifact disk
                               |
                               v
                        Redpanda Cloud
```

The production browser never calls `localhost`. The static console builds with an empty `VITE_API_URL`, so all requests are relative to its own public origin. Render rewrite rules proxy `/api/*` and `/health` to the public FastAPI service.

## Why this removes Docker as a deployment dependency

`render.yaml` uses only native Render runtimes:

- `runtime: static` for the Vite console
- `runtime: python` for FastAPI and all workers
- Render-managed Postgres
- Redpanda Cloud for Kafka-compatible streaming

Dockerfiles and Compose files can remain in the repository as optional local/infrastructure references, but they are not used by the cloud deployment.

## 1. Create Redpanda Cloud credentials

Create a Redpanda Cloud cluster and a SASL user using `SCRAM-SHA-256`.

Record these three values:

- Kafka bootstrap server, for example `seed-...:9092`
- SASL username
- SASL password

FleetMind expects TLS/SASL in cloud mode:

```text
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-256
```

### Required access

The FleetMind service account must be able to:

- connect to the Kafka API
- create or access `vehicle.telemetry.v1`
- create or access `vehicle.failure-events.v1`
- produce to both topics
- consume from both topics
- use the `fleetmind-reliability-worker-v2` consumer group

The cloud worker calls `ensure_fleetmind_topics()` before starting. If your Redpanda account does not have topic-create permission, create both topics in Redpanda Cloud first and set:

```text
KAFKA_AUTO_CREATE_TOPICS=false
```

Use three partitions for each topic. Redpanda Cloud normally manages replication for the cluster; the Blueprint defaults to replication factor 3 when auto-creation is enabled.

## 2. Merge the cloud runtime branch

The Render Blueprint is intended to live on the repository's default deployment branch. After validation, merge `feature/fleetmind-cloud-runtime` after the Experience V2 dependency it is based on.

## 3. Create the Render Blueprint

In Render:

1. Choose **New > Blueprint**.
2. Connect `munnamihir/fleetmind`.
3. Render detects `render.yaml` at the repository root.
4. Review the services and database.
5. During the initial Blueprint creation, Render prompts for values marked `sync: false`.

For both `fleetmind-worker-munnamihir` and `fleetmind-simulator-munnamihir`, enter the same Redpanda values:

```text
KAFKA_BOOTSTRAP_SERVERS=<redpanda-bootstrap-host:port>
KAFKA_SASL_USERNAME=<redpanda-user>
KAFKA_SASL_PASSWORD=<redpanda-password>
```

Do not commit these credentials to Git.

## 4. Resources created by the Blueprint

### Public console

Service:

```text
fleetmind-munnamihir
```

Expected public URL:

```text
https://fleetmind-munnamihir.onrender.com
```

This is the URL you can open from any browser, phone, tablet, or computer.

### Public API

Service:

```text
fleetmind-api-munnamihir
```

Expected API URL:

```text
https://fleetmind-api-munnamihir.onrender.com
```

Health endpoint:

```text
https://fleetmind-api-munnamihir.onrender.com/health
```

The console normally reaches this API through Render rewrite rules, not directly.

### Database

`fleetmind-postgres-munnamihir` is a managed Render Postgres instance. Public database ingress is disabled in the Blueprint. Render services receive its private `connectionString` automatically.

FleetMind normalizes provider-style `postgresql://...` URLs to SQLAlchemy's `postgresql+psycopg://...` form so psycopg 3 is used consistently.

### Workers

- `fleetmind-worker-munnamihir` consumes telemetry/failure events and persists evidence.
- `fleetmind-simulator-munnamihir` continuously produces the simulated fleet stream.
- `fleetmind-ml-munnamihir` trains/evaluates the existing FleetMind ML pipeline.

The ML worker owns a persistent Render disk at:

```text
/var/data/fleetmind-artifacts
```

so model artifacts survive worker redeploys.

## 5. First-deploy verification

Check the API first:

```bash
curl -fsS https://fleetmind-api-munnamihir.onrender.com/health
```

Expected response contains a healthy/ok FleetMind API status.

Then open:

```text
https://fleetmind-munnamihir.onrender.com
```

In the UI verify:

- command bar reports API LIVE
- Fleet data begins populating
- telemetry event count increases
- alerts appear as the simulator generates evidence
- Diagnostics views load
- My Work loads without a repeating unpinned outcome-summary 503
- browser Network requests use the FleetMind Render hostname, never localhost

## 6. Service logs to inspect

### Worker

Expected startup behavior:

```text
consuming telemetry=vehicle.telemetry.v1 failure_truth=vehicle.failure-events.v1
```

### Simulator

Expected startup behavior:

```text
FleetMind simulator: 500 vehicles -> vehicle.telemetry.v1
```

### ML trainer

The trainer waits for sufficient persisted telemetry before producing a defensible run. An `insufficient_evidence` benchmark state is valid and must not be manually promoted.

## 7. Production truth boundaries remain unchanged

Moving FleetMind to the cloud does not change its scientific or operational semantics:

- correlation is not causality
- attention is not physical failure probability
- model confidence/prediction horizon is not confirmed physical RUL
- workflow execution is not physical repair
- observed post-execution improvement is not proof the action caused the improvement
- human acknowledgment/approval/execution gates remain mandatory
- no autonomous physical-control behavior is introduced

## 8. Optional custom domain

After the default Render URL is healthy, attach a custom domain to the static console, for example:

```text
fleetmind.example.com
```

Keep the API behind the static site's `/api/*` and `/health` rewrite path. This avoids exposing frontend code to environment-specific API origins and keeps the browser on one origin.

## 9. Cost / scaling note

Render background workers are continuously running compute and therefore require a paid worker plan. The Blueprint intentionally uses small baseline worker plans and a larger ML worker. Increase compute only after measuring actual CPU/memory pressure. The simulator event rate can also be reduced with `SIM_EVENTS_PER_SECOND` if the goal is a public demo rather than a sustained load test.
