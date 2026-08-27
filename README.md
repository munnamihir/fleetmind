# FleetMind

> **Detect failures before fault codes do — then turn evidence into human-controlled fleet decisions.**

FleetMind is an open-source reliability-intelligence and fleet-operations platform for physical fleets: EVs, robots, chargers, energy systems, and industrial machines. The first vertical is a synthetic EV fleet with intentionally hidden coolant-pump degradation and firmware-interaction scenarios.

FleetMind streams observable vehicle telemetry through Kafka-compatible Redpanda, persists engineering evidence in PostgreSQL, evaluates reliability and predictive-maintenance models, builds diagnostic timelines and cases, derives fleet-level operational intelligence, and exposes the result through a React engineering console.

The project deliberately separates **observable evidence**, **private synthetic failure truth**, **model outputs**, **workflow state**, and **human decisions** so the UI can be useful without overstating causality.

## Current status

**Current milestone: Phase 8.1 complete — Fleet Command, decision-queue ownership, closed-loop recommendation materialization, and dashboard navigation/polling hardening.**

The current end-to-end stack is:

```text
Synthetic EV Fleet
      │
      ├── observable telemetry
      │
      └── private failure truth (evaluation only)
      ▼
Redpanda / Kafka
      ▼
Risk + persistence worker
      ▼
PostgreSQL
      ├── telemetry / alerts / failure truth
      ├── model runs / predictions / benchmark lineage
      ├── diagnostic events / episodes / cases
      ├── maintenance / automation / fleet decision state
      └── closed-loop recommendations / audit activity
      ▼
FastAPI
      ▼
React Engineering Console
      ├── Fleet Overview
      ├── Incidents
      ├── Reliability
      ├── Cohorts
      ├── Components
      ├── Firmware
      ├── Predictive ML
      └── Root Cause
            └── Fleet Command
                  ├── Command Center
                  ├── Explainability
                  ├── Decision Queue
                  └── Closed Loop
```

### Recently completed

- Phase 8.0 closed-loop operations foundation
- Phase 8.1 decision-queue ownership and human-controlled workflow transitions
- Deterministic recommendation materialization with database uniqueness
- Application-level idempotency plus concurrent insert race protection with savepoints
- Explicit recommendation audit activity
- Selected-vehicle-only persistent materialization
- Human approval and execution gates
- Fleet Command evidence explainability and attention decomposition
- Nested tabs across all left-navigation dashboards
- Nested views inside Fleet Command
- Active-page polling: inactive left-side pages no longer fetch continuously
- Lazy mounting of heavy Root Cause modules
- Active-workspace polling inside Fleet Command
- QueuePool exhaustion fixed at the source instead of increasing database pool limits

## What makes the demo different

The simulator **does not publish a failure label** in normal telemetry. A latent coolant-pump defect changes observable physics over time:

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

FleetMind must infer degradation from telemetry and only uses the private failure stream for controlled evaluation.

The same truth boundary carries through later phases:

```text
observable evidence
      ↓
model / deterministic analysis
      ↓
diagnostic hypothesis
      ↓
human-controlled workflow recommendation
```

FleetMind does **not** equate:

- attention score with physical failure probability
- workflow lineage with physical causality
- recommendation execution with physical repair
- post-workflow change with proof that maintenance caused recovery

## Capability map

### 1. Streaming fleet telemetry

- Synthetic multi-vehicle EV telemetry
- Firmware, factory, model, mileage, environment, and component-revision metadata
- Hidden degradation scenarios
- Kafka-compatible Redpanda event transport
- PostgreSQL persistence
- Docker Compose local environment
- Experiment identity and simulator reset/epoch handling

### 2. Reliability science

- Private ground-truth failure stream for evaluation only
- Right-censored two-parameter Weibull fitting
- B10/B50 and characteristic life
- Kaplan-Meier survival curves
- Early-warning detection rate
- Lead-mileage and accelerated-time metrics
- Pump-revision reliability comparison
- Failure and warning drill-down

### 3. Firmware regression intelligence

- Treatment/control firmware comparison
- Coarsened exact matching by hardware, mileage, and environment
- Risk ratios, intervals, absolute risk increase
- Cochran-Mantel-Haenszel association testing
- Hardware × firmware interaction analysis
- Regression classification
- Firmware engineering console

### 4. Predictive Maintenance ML

- Rolling telemetry feature windows
- Prospective future-horizon labels
- Right-censoring protection
- Sensor-only XGBoost classifier
- Logistic-regression baseline
- Vehicle-isolated deterministic development/benchmark splits
- Validation-derived operational threshold
- Optional Platt calibration when supported
- ROC-AUC, PR-AUC, precision, recall, F1, Brier score
- Confusion matrix and calibration views
- Early-warning lead-distance evaluation
- Persisted model runs and predictions
- Frozen benchmark snapshot after evidence qualification
- SHA-256 dataset and feature-schema integrity
- Model-lineage-aware longitudinal prediction history
- Experiment-epoch continuity guards

### 5. Diagnostic and Root Cause Intelligence

FleetMind now extends beyond one risk score into a layered diagnostic workflow:

- Diagnostic event generation with anti-chatter behavior
- Event transitions
- Temporal diagnostic episodes
- Diagnostic cases and workflow status
- Replay and extended replay
- Evidence-backed hypothesis ranking
- Cross-case pattern intelligence
- Similar-case lookup
- Watchlists and saved investigation views
- Prognostic trajectory analysis
- Experimental model-confidence horizons
- Maintenance planning workflow
- Operational automation with explicit approval
- Fleet-level decision intelligence
- Vehicle operational digital twin
- Fleet capacity/planning intelligence
- Fleet change snapshots and comparisons
- Workflow-effectiveness analysis

### 6. Fleet Command & Closed Loop

Fleet Command turns the diagnostic stack into an operator workspace while preserving human control.

Current workspaces:

```text
Command Center
  ├── Overview
  ├── Operator Queues
  ├── Cohorts
  └── Attention Factors

Explainability
  ├── Overview
  ├── Attention
  ├── Evidence
  └── Lineage

Decision Queue
  ├── Overview
  ├── Active Queue
  ├── Ownership
  └── Workflow Status

Closed Loop
  ├── Evaluate
  ├── Evaluation Results
  ├── Recommendations
  └── Lifecycle
```

Closed-loop recommendation lifecycle:

```text
PROPOSED
   ↓
ACKNOWLEDGED
   ↓
APPROVAL_REQUIRED
   ↓
APPROVED
   ↓
EXECUTION_READY
   ↓
EXECUTED
```

Persistent materialization is intentionally restricted to the explicitly selected vehicle. Preview evaluation can inspect the wider selected run without writing recommendations.

The lifecycle controls workflow metadata only. It does not send a physical vehicle command and does not prove that physical maintenance occurred.

## Dashboard navigation

The React console uses two navigation levels.

### Left navigation

- Fleet Overview
- Incidents
- Reliability
- Cohorts
- Components
- Firmware
- Predictive ML
- Root Cause

### Page-level nested tabs

Each major page now exposes its component groups as internal tabs instead of stacking every panel vertically. Root Cause uses a horizontally scrollable tab row for its larger intelligence set.

Heavy Root Cause modules are mounted only when their tab is active. This prevents hidden components from continuing their polling loops.

`App.tsx` also fetches only the data required by the active left-side page. Fleet Command polls only its active workspace. This avoids the database connection fan-out that previously produced SQLAlchemy `QueuePool` timeout bursts.

## Run locally

Requirements:

- Docker Desktop
- Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Open:

- FleetMind console: `http://localhost:5173`
- FastAPI docs: `http://localhost:8000/docs`
- API health: `http://localhost:8000/health`

The default simulation can be scaled through `.env`:

```text
SIMULATED_VEHICLES=5000
SIM_EVENTS_PER_SECOND=1000
SIM_TIME_ACCELERATION=600
```

## Useful verification

Basic service state:

```bash
docker compose ps
```

Recent API failures:

```bash
docker compose logs api --since=5m \
  | grep -E 'QueuePool|TimeoutError|500 Internal'
```

Core Fleet Command contracts:

```bash
PYTHONPATH=services/common \
python3 -m unittest discover \
  -s tests \
  -p 'test_fleet_command_closed_loop.py' \
  -v
```

Closed-loop concurrency contract:

```bash
PYTHONPATH=services/common \
python3 -m unittest discover \
  -s tests \
  -p 'test_closed_loop_materialization_concurrency.py' \
  -v
```

Nested dashboard behavior:

```bash
python3 -m unittest discover \
  -s tests \
  -p 'test_nested_tabs_active_polling.py' \
  -v
```

## API families

FleetMind exposes more endpoints than the short list below; use FastAPI `/docs` for the complete live contract.

### Fleet / reliability / firmware

```text
GET /health
GET /api/v1/fleet/summary
GET /api/v1/alerts
GET /api/v1/vehicles/{vehicle_id}
GET /api/v1/cohorts/pump-revisions
GET /api/v1/reliability/pump-revisions
GET /api/v1/reliability/failures
GET /api/v1/firmware/overview
GET /api/v1/firmware/regression
```

### Predictive ML

```text
GET /api/v1/ml/status
GET /api/v1/ml/benchmark
GET /api/v1/ml/predictions
GET /api/v1/ml/vehicles/{vehicle_id}
GET /api/v1/ml/vehicles/{vehicle_id}/history
```

### Diagnostics and fleet intelligence

Representative families include:

```text
/api/v1/diagnostics/status
/api/v1/diagnostics/events
/api/v1/diagnostics/episodes
/api/v1/diagnostics/cases
/api/v1/diagnostics/patterns
/api/v1/diagnostics/prognostics
/api/v1/diagnostics/maintenance
/api/v1/diagnostics/automation
/api/v1/diagnostics/fleet-intelligence
/api/v1/diagnostics/twins
/api/v1/diagnostics/fleet-twin
/api/v1/diagnostics/workflow-effectiveness
/api/v1/diagnostics/fleet-command
/api/v1/diagnostics/explainability
/api/v1/diagnostics/decision-queue
/api/v1/diagnostics/closed-loop
```

## Repository

```text
fleetmind/
├── docker-compose.yml
├── README.md
├── ROADMAP.md
├── docs/
│   └── ARCHITECTURE.md
├── services/
│   ├── common/fleetmind_common/
│   │   ├── benchmark_snapshot.py
│   │   ├── capacity_planning_rules.py
│   │   ├── closed_loop_rules.py
│   │   ├── decision_queue_rules.py
│   │   ├── diagnostic_*_rules.py
│   │   ├── diagnostic_store.py
│   │   ├── evidence_explainability_rules.py
│   │   ├── firmware.py
│   │   ├── fleet_*_rules.py
│   │   ├── ml_features.py
│   │   ├── reliability.py
│   │   ├── vehicle_twin_rules.py
│   │   └── workflow_effectiveness_rules.py
│   ├── api/
│   ├── worker/
│   ├── simulator/
│   └── ml/
├── web/
│   └── src/
│       ├── App.tsx
│       ├── DashboardPageTabs.tsx
│       ├── RootCauseDashboard.tsx
│       ├── FleetCommandOperations.tsx
│       └── intelligence modules...
└── tests/
```

## Current engineering boundary

FleetMind is a synthetic engineering platform and portfolio system. Its statistical and ML outputs should be read in that context.

The strongest claims the platform currently supports are about:

- observed telemetry
- synthetic failure evaluation
- benchmarked model behavior
- deterministic workflow state
- reproducible evidence lineage
- operator-controlled recommendation lifecycle

It should not make unsupported claims about:

- real Tesla vehicles or proprietary Tesla data
- physical causality from correlation alone
- calibrated physical remaining useful life unless explicitly implemented and validated
- physical repair completion from workflow execution
- failure prevention from a recommendation being executed

## What comes next

The planned next sequence is:

```text
Phase 8.2  Closed-Loop Outcome Verification
Phase 8.3  Closed-Loop Effectiveness Analytics
Phase 8.4  Recommendation Policy Evaluation
Phase 8.5  Shadow-Mode Policy Experimentation
Phase 9.0  Fleet Reliability Intelligence Platform
```

Phase 8.2 will add first-class post-execution observation: baseline vs post-workflow evidence, deterministic outcome classification, idempotent outcome materialization, and an Outcomes view in Fleet Command. It will describe **observed improvement/stability/worsening**, not claim that a workflow physically repaired a vehicle.

See [ROADMAP.md](ROADMAP.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
