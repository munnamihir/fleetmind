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

## Current milestone: Phase 5.1 predictive-maintenance benchmark hardening

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
- Firmware treatment/control cohort comparison
- Coarsened exact matching by component revision, mileage band and environment
- Cochran–Mantel–Haenszel significance testing and effect-size estimates
- Hardware × firmware interaction analysis
- Firmware Regression Lab dashboard
- Rolling telemetry feature windows with right-censoring protection
- Sensor-only XGBoost predictive-maintenance baseline
- Vehicle-isolated, late-life held-out evaluation
- Validation-derived alert threshold targeting ~2% false-positive rate
- Optional Platt probability calibration when validation support is sufficient
- ROC-AUC, PR-AUC, precision/recall/F1, Brier score and confusion matrix
- ML early-warning lead-distance evaluation
- Persisted model runs, feature importance and live vehicle predictions
- Predictive Maintenance ML dashboard

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
GET /api/v1/firmware/overview
GET /api/v1/firmware/regression?target=2026.32.4&control=2026.32.1
GET /api/v1/ml/status
GET /api/v1/ml/benchmark
GET /api/v1/ml/predictions?limit=25
GET /api/v1/ml/vehicles/{vehicle_id}
GET /api/v1/ml/vehicles/{vehicle_id}/history?limit=60
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
│   │   ├── reliability.py
│   │   ├── firmware.py
│   │   ├── ml_features.py
│   │   └── risk.py
│   ├── api/
│   ├── worker/
│   ├── simulator/
│   └── ml/
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

## Firmware regression intelligence v0.3

Phase 4 adds a synthetic OTA regression scenario affecting CP-17 coolant pumps on firmware `2026.32.4`. The failure cause remains private simulator truth; the analysis layer only sees ordinary firmware metadata, telemetry and observed failure events.

FleetMind compares `2026.32.4` against `2026.32.1` using coarsened exact matching on component revision, 40k-mile odometer band and ambient-temperature band. It reports raw matched failure rates, risk ratio with a 95% interval, absolute risk increase, a Mantel-Haenszel common odds ratio, Cochran-Mantel-Haenszel significance, supportive telemetry deltas, and hardware × firmware interactions.

The simulator intentionally uses a larger CP-17 cohort in this demo milestone so a 500-vehicle local run can accumulate enough failures to exercise the statistical workflow. Treat all results as synthetic experiment output, not real Tesla data.

## Predictive maintenance ML v0.5

Phase 5.1 predicts whether a coolant-pump failure will occur within the next `ML_FAILURE_HORIZON_MILES` (2,500 miles by default) from rolling telemetry windows while separating operational scoring from benchmark claims. The fitted models are intentionally denied FleetMind's rule-engine outputs: `risk_score`, `status`, alerts, fault codes, vehicle identity and failure-event fields are not model inputs. Firmware/revision/factory/model remain available as display context but are excluded from fit.

Training examples are prospective. Features use telemetry at or before the window anchor; the label asks whether the private failure event occurs after the anchor and within the future mileage horizon. Healthy-looking windows without enough future observed mileage are treated as right-censored and dropped instead of being mislabeled as negatives.

The benchmark cohort is frozen by a deterministic SHA-256 hash of `vehicle_id` using a fixed seed. Membership is label-agnostic, so a vehicle cannot enter or leave the benchmark when it later fails. Benchmark vehicles are never used for model fitting, Platt calibration or threshold selection. The operating threshold still comes only from validation negatives, targeting roughly a 2% validation false-positive rate.

Every complete run evaluates both sensor-only XGBoost and a sensor-only logistic-regression baseline on the exact same frozen benchmark. FleetMind reports ROC-AUC, PR-AUC, precision, recall, F1, Brier score, confusion matrices, calibration, early-warning lead mileage and XGBoost-vs-baseline deltas. A benchmark qualification gate blocks headline claims until the frozen cohort has at least 1,000 eligible windows, 20 positive windows, 8 distinct failure vehicles and both classes. Operational live predictions continue even if the benchmark is not yet qualified.

Historical `ml_predictions` rows are retained intentionally and exposed through the vehicle-history API so the dashboard can visualize longitudinal risk instead of treating older model-run predictions as duplicates. Serialized XGBoost and logistic-regression artifacts are stored in the ML Docker volume.

See [ROADMAP.md](ROADMAP.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Design goal

FleetMind should feel like software an engineer uses to answer:

> *What is failing, which population is affected, why do we believe it, how early did we know, and what should engineering investigate next?*
