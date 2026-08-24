# FleetMind

> **Detect failures before fault codes do.**

FleetMind is an open-source reliability-intelligence platform for physical fleets: EVs, robots, chargers, energy systems and industrial machines. The first vertical is a synthetic EV fleet with an intentionally hidden coolant-pump degradation scenario.

The system streams vehicle telemetry through Kafka-compatible Redpanda, detects multi-signal degradation, persists engineering evidence, identifies risky component cohorts and exposes the results through a live reliability console.

## What makes the demo different

The simulator **does not publish a failure label**. A latent CP-17 coolant-pump defect changes observable physics over time:

```text
pump current ↑
      ↓
pump RPM ↓
      ↓
coolant efficiency ↓
      ↓
battery temperature ↑
      ↓
eventual fault
```

FleetMind must infer the problem from telemetry.

## Current milestone: Phase 2 reliability science

```text
Synthetic fleet ─► Redpanda/Kafka ─► Risk worker ─► PostgreSQL ─► FastAPI ─► React console
```

### Included now

- Synthetic multi-vehicle EV telemetry
- Hidden component degradation influenced by mileage and heat
- Firmware, factory and component-revision metadata
- Kafka-compatible streaming
- Explainable multi-signal anomaly score
- Live alert generation
- Fleet-health summary
- Component cohort comparison
- Vehicle telemetry history API
- Dark engineering-focused dashboard
- Docker Compose local environment with automatic Kafka topic initialization
- Private ground-truth component failure stream for evaluation only
- Right-censored two-parameter Weibull reliability fitting
- B10/B50 and characteristic-life estimates
- Kaplan-Meier survival curves
- Early-warning detection rate and lead-time/mileage metrics

## Run

Requirements: Docker Desktop + Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Open:

- FleetMind console: `http://localhost:5173`
- FastAPI docs: `http://localhost:8000/docs`
- API health: `http://localhost:8000/health`

The default simulation produces 500 vehicles and ~120 telemetry events/sec. Change those in `.env`:

```text
SIMULATED_VEHICLES=5000
SIM_EVENTS_PER_SECOND=1000
SIM_TIME_ACCELERATION=600
```

## Demo storyline

1. Start the stack.
2. Watch telemetry event count rise.
3. Healthy CP-15/CP-16 vehicles establish a baseline.
4. CP-17 vehicles operating under higher heat/mileage begin showing pump-current and RPM drift.
5. FleetMind raises explainable anomaly alerts.
6. The component cohort panel surfaces CP-17 as the higher-risk population.
7. Drill into a vehicle using `GET /api/v1/vehicles/{vehicle_id}` to inspect its recent telemetry history.

## APIs

```text
GET /health
GET /api/v1/fleet/summary
GET /api/v1/alerts?limit=20
GET /api/v1/vehicles/{vehicle_id}
GET /api/v1/cohorts/pump-revisions
GET /api/v1/reliability/pump-revisions
GET /api/v1/reliability/failures?limit=50
```

## Repository

```text
fleetmind/
├── docker-compose.yml
├── ROADMAP.md
├── docs/
│   └── ARCHITECTURE.md
├── services/
│   ├── common/fleetmind_common/
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models.py
│   │   └── risk.py
│   ├── api/
│   ├── worker/
│   └── simulator/
├── web/
│   └── src/
└── tests/
```

## Risk engine v1

The current risk model is intentionally transparent. It combines evidence from:

- Coolant-pump current
- Coolant-pump RPM
- Coolant temperature
- Battery temperature
- Cell-voltage imbalance
- Inverter temperature

This is a baseline, not the final ML model. The roadmap moves from explainable rules to evaluated classifiers, survival analysis and remaining-useful-life estimation while retaining evidence traces.

## Reliability science v0.2

The simulator publishes observable telemetry and private evaluation truth to separate Kafka topics. The worker stores the truth only in `failure_events`; it is never part of the telemetry contract used by the risk engine.

For each pump revision, FleetMind treats failed vehicles as observed lifetimes and healthy vehicles as right-censored lifetimes. The API fits a two-parameter Weibull distribution, returns β/η/B10/B50, generates a Kaplan-Meier curve, and measures how far before failure the first degraded/critical telemetry signal appeared.

`SIM_TIME_ACCELERATION=600` means one wall-clock second represents 600 seconds of accelerated fleet operation so useful field-life statistics emerge during a short local demo.

See [ROADMAP.md](ROADMAP.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Design goal

FleetMind should feel like software an engineer uses to answer:

> *What is failing, which population is affected, why do we believe it, how early did we know, and what should engineering investigate next?*
