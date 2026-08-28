# FleetMind Architecture

## Architecture status

FleetMind has evolved from a streaming reliability demo into a layered reliability-intelligence and human-controlled fleet-operations system.

The current implementation includes:

- streaming telemetry and private synthetic failure truth
- reliability and firmware analysis
- predictive-maintenance ML with benchmark lineage
- diagnostic events, episodes, replay, and cases
- fleet pattern and prognostic intelligence
- maintenance and guarded workflow automation
- vehicle operational twins and fleet decision intelligence
- Fleet Command
- evidence explainability
- decision-queue ownership
- closed-loop recommendation materialization
- human-controlled lifecycle transitions
- dashboard nested navigation with active polling

The roadmap implementation is now delivered through Phase 9.5. Closed-loop outcome observation, effectiveness analytics, policy replay/shadow experimentation, platform observability, scale/recovery harnesses, deployment engineering, model ops and multi-asset reliability are integrated. Empirical throughput, production SLO and RPO/RTO claims remain environment-dependent.

---

## Current data path

```text
                         SYNTHETIC EV FLEET
                               │
             ┌─────────────────┴──────────────────┐
             │                                    │
             │ observable telemetry               │ private failure truth
             │                                    │ evaluation only
             ▼                                    ▼
                     Redpanda / Kafka topics
                               │
                               ▼
                       Risk / persistence worker
                               │
                               ▼
                           PostgreSQL
             ┌─────────────────┼──────────────────────┐
             │                 │                      │
             ▼                 ▼                      ▼
        Fleet state       ML / benchmark       Diagnostic store
        telemetry         predictions          events / episodes
        alerts            lineage              cases / workflow
        failures          snapshots            recommendations
             │                 │                      │
             └─────────────────┼──────────────────────┘
                               ▼
                            FastAPI
                               │
                               ▼
                    React Engineering Console
```

The architecture deliberately keeps private synthetic truth out of normal telemetry and out of operational recommendation inputs unless an endpoint is explicitly an offline/evaluation path.

---

## Runtime services

### `simulator`

Produces synthetic EV telemetry and maintains latent degradation/failure mechanisms.

Responsibilities:

- vehicle population generation
- mileage progression
- thermal/pump signals
- firmware / factory / model / revision context
- hidden degradation
- experiment identity
- private evaluation truth

### Redpanda

Kafka-compatible event transport.

Responsibilities:

- telemetry topic
- failure/evaluation topic
- decoupled producer/consumer flow
- replayable event transport

### `worker`

Consumes observable telemetry and private truth through their separate contracts.

Responsibilities:

- telemetry persistence
- explainable risk calculation
- alert generation
- failure-truth persistence
- experiment scoping

### PostgreSQL

Authoritative persistence for:

- telemetry
- alerts
- synthetic failure truth
- ML runs and predictions
- benchmark metadata
- diagnostic events
- diagnostic episodes
- diagnostic cases
- maintenance plans
- watchlists / views
- automation policies and actions
- fleet snapshots
- operational twin snapshots
- closed-loop recommendations
- recommendation audit activity

### `ml-trainer`

Builds deterministic training/evaluation datasets and predictive-maintenance runs.

Responsibilities:

- rolling feature windows
- future-horizon labels
- right-censoring handling
- development/validation/benchmark partitioning
- XGBoost and logistic-regression baseline
- calibration / threshold selection
- locked benchmark snapshot
- model lineage
- diagnostic replay/backfill jobs

### FastAPI

Provides the public engineering and operational API layer.

Major API families:

- fleet
- alerts
- vehicles
- reliability
- firmware
- ML
- diagnostics
- cases
- patterns
- prognostics
- maintenance
- automation
- fleet intelligence
- vehicle twins
- fleet twin
- workflow effectiveness
- Fleet Command
- explainability
- decision queue
- closed loop

### React console

Provides engineering and operator workflows.

Top-level pages:

```text
Fleet Overview
Incidents
Reliability
Cohorts
Components
Firmware
Predictive ML
Root Cause
```

Each page uses internal tabs to avoid large stacked dashboards.

Root Cause contains the diagnostic and fleet-intelligence modules, including Fleet Command.

---

# Data and claim boundaries

## Observable telemetry vs private truth

Telemetry deliberately contains observable engineering measurements and deployment metadata, not a direct `failed` or `is_degraded` label.

Key telemetry context includes:

- vehicle ID
- model
- factory
- firmware
- mileage
- component revision
- ambient temperature
- speed
- battery signals
- inverter/motor signals
- coolant temperature
- coolant-pump RPM/current

Private failure truth is stored separately and is intended for synthetic evaluation.

```text
observable telemetry ──────────────► operational analysis
private synthetic truth ───────────► controlled evaluation
```

## Engineering evidence vs causality

FleetMind can show that signals co-occur, that a cohort is enriched, that a model assigns confidence, or that workflow state changed.

Those facts do not by themselves prove a physical causal mechanism.

## Workflow state vs physical state

FleetMind closed-loop execution currently means **workflow execution**.

It does not:

- send a command to a real vehicle
- prove that a technician performed a repair
- mutate simulated physical condition as a consequence of a recommendation
- establish that maintenance caused later telemetry changes

---

# Reliability analysis boundary

For pump-revision reliability, FleetMind treats observed synthetic failures as lifetimes and non-failed vehicles as right-censored observations.

Current outputs include:

- Weibull β / η
- B10 / B50
- reliability at selected mileage points
- Kaplan-Meier curve
- observed failure rate
- early-warning detection rate
- lead mileage
- accelerated-time lead

These are synthetic-experiment reliability outputs, not real-world OEM reliability claims.

---

# Firmware regression architecture

Firmware comparison builds matched treatment/control observations from the current experiment.

The analysis uses deployment and telemetry context such as:

- pump revision
- mileage band
- ambient-temperature band
- firmware

Outputs include:

- matched population
- target/control failure counts
- target/control failure rates
- risk ratio and interval
- absolute risk increase
- Mantel-Haenszel common odds ratio
- Cochran-Mantel-Haenszel statistic / p-value
- supportive telemetry deltas
- hardware × software interactions

The private simulator cause is not exposed as an operational model feature.

---

# Predictive ML boundaries

## Prospective feature/label contract

```text
telemetry at or before anchor
          │
          ▼
rolling sensor features
          │
          ▼
model input
          │
          └──────── asks about future failure horizon
```

A window is positive only when an eligible private synthetic failure occurs after the anchor and within the configured future mileage horizon.

A healthy-looking window without enough future observation is right-censored rather than forced into the negative class.

## Development vs benchmark

```text
eligible causal windows
        │
        ├── development train vehicles
        │
        ├── development validation vehicles
        │
        └── frozen benchmark vehicles
```

Benchmark vehicle membership is deterministic and label-agnostic.

Within development data, validation assignment can be group-stratified by causal support while keeping each vehicle in one partition.

## Locked benchmark snapshot

A frozen vehicle cohort alone is not an immutable test dataset because more causal windows can accumulate.

FleetMind therefore locks an exact benchmark snapshot once the evidence gate qualifies:

```text
frozen benchmark vehicle IDs
          │
          ▼
eligible benchmark windows
          │
          │ qualification passes
          ▼
LOCKED BENCHMARK SNAPSHOT
  - exact feature rows
  - labels
  - anchor timestamp / mileage
  - data SHA-256
  - feature-schema SHA-256
          │
          ▼
later runs in the same lineage
use the same evaluation artifact
```

Missing/tampered snapshots or incompatible feature schemas fail closed.

## Lineage and experiment epochs

Historical model predictions are comparable only inside a compatible model lineage and mileage-continuous experiment epoch.

Large backward odometer jumps create a new epoch.

Feature windows cannot cross that boundary, and failure truth from a prior epoch cannot become future truth for a new experiment.

---

# Diagnostic architecture

The diagnostic stack turns isolated model/evidence observations into reproducible investigation state.

```text
model + telemetry evidence
          │
          ▼
     diagnostic event
          │
          ▼
       transition
          │
          ▼
        episode
          │
          ▼
          case
          │
          ├── evidence / hypothesis
          ├── assignment / workflow
          ├── watchlist / views
          └── replay
```

## Events

Events represent diagnostic evidence/state changes with anti-chatter behavior.

## Episodes

Episodes group related events across time into a longitudinal diagnostic context.

## Cases

Cases provide the human investigation/workflow layer.

They track operational status, review priority, assignment, evidence, and activity without claiming that a case label is a physical-failure diagnosis.

## Replay

Replay reconstructs run-frozen diagnostic evidence and state so investigations can be reproduced.

---

# Fleet intelligence architecture

FleetMind derives several higher-level operational views from run-frozen diagnostic and workflow records.

## Fleet Pattern Intelligence

```text
cases
  ├── hypothesis
  ├── firmware
  ├── factory
  ├── pump revision
  └── model
        ↓
hotspots / recurring clusters / similar cases
```

These are descriptive investigation shortcuts, not causal enrichment.

## Prognostics & Maintenance Intelligence

The prognostic layer fits trajectories of model-hypothesis confidence against mileage and may extrapolate toward a configured model-confidence threshold.

```text
historical model confidence
          ↓
run-frozen trajectory fit
          ↓
experimental threshold horizon
          ↓
maintenance review queue
```

This is intentionally **not physical remaining useful life**.

Maintenance plans are operator-owned workflow records.

## Operational Automation

Automation evaluates deterministic, source-versioned policies against run-frozen operational evidence.

Lifecycle:

```text
dry-run simulation
      ↓
explicit evaluate
      ↓
PENDING_APPROVAL
      ↓
human approve/reject
      ↓
explicit execute
```

Execution is limited to guarded workflow metadata effects. No automatic physical action occurs.

## Vehicle Operational Twin

The vehicle operational twin unifies:

- model state
- diagnostic state
- case state
- prognostic state
- maintenance state
- automation state
- fleet-decision state
- coverage state

It provides a timeline, lineage graph, evidence inventory, checkpoints, and comparison.

It is an **operational twin**, not a physics twin.

## Fleet Decision Intelligence

Fleet decision state combines current-run model outputs with persisted diagnostic/workflow records.

Outputs include:

- deterministic decision state
- attention score
- workflow load units
- coverage gaps
- queue ordering
- cohort concentration
- no-write scenario simulation
- versioned checkpoints

Attention score is not a physical failure probability.

---

# Fleet Command architecture

Fleet Command is the operator-facing aggregation of the fleet-intelligence stack.

```text
                FLEET COMMAND
                      │
        ┌─────────────┼──────────────────┐
        ▼             ▼                  ▼
 Command Center   Explainability    Decision Queue
        │             │                  │
        └─────────────┼──────────────────┘
                      ▼
                  Closed Loop
```

## Command Center

Provides:

- fleet-level metrics
- operator queue groups
- cohort analysis
- deterministic attention factors

## Explainability

Provides:

- vehicle attention decomposition
- evidence inventory
- workflow/evidence lineage

The lineage is a data/workflow lineage, not a physical causal graph.

## Decision Queue

Provides:

- active recommendation queue
- ownership
- lifecycle/status grouping
- assignment/unassignment
- explicit operator transitions

## Closed Loop

Recommendation evaluation can be previewed without persistence.

Persistent materialization is intentionally restricted to an explicitly selected vehicle.

```text
candidate evidence
      ↓
deterministic recommendation key
      ↓
PROPOSED recommendation
      ↓
CREATED audit activity
```

The database enforces recommendation-key uniqueness.

Normal duplicate requests are caught through a bulk existing-key lookup. A narrower concurrent insert race is isolated in a database savepoint; if another request wins the unique-key race, FleetMind reloads the existing recommendation rather than returning a duplicate-write failure.

Recommendation and `CREATED` audit activity are flushed atomically inside the savepoint.

## Lifecycle guardrail

```text
PROPOSED
   ↓ acknowledge
ACKNOWLEDGED
   ↓ request approval
APPROVAL_REQUIRED
   ↓ approve
APPROVED
   ↓ mark ready
EXECUTION_READY
   ↓ explicit execute workflow
EXECUTED
```

There is no automatic approval and no automatic execution.

---

# Frontend navigation and polling architecture

The dashboard uses nested tabs across the left-navigation pages.

The initial nested-tab implementation hid panels visually but kept heavy Root Cause components mounted. Because many modules have their own polling loops, hidden modules continued to hit the API and temporarily exhausted SQLAlchemy's default connection pool.

The corrected architecture is:

```text
active left page
      ↓
only that page's shared data polling

Root Cause selected
      ↓
only active heavy Root Cause module mounted

Fleet Command selected
      ↓
only active Fleet Command workspace polling
```

This keeps React Strict Mode enabled and fixes request fan-out without masking the problem by increasing `pool_size` or `max_overflow`.

Inactive heavy modules are intentionally unmounted.

---

# Database and idempotency principles

FleetMind uses PostgreSQL plus SQLAlchemy.

Important rules:

1. Database uniqueness is the final source of truth for idempotent materialization.
2. Application-level lookups handle the normal repeat-request path efficiently.
3. Concurrent insert races are handled explicitly rather than assumed away.
4. Audit activity should remain transactionally consistent with the state it describes.
5. Pool-size increases should not be used to compensate for unnecessary frontend request fan-out.

---

# Current UI hierarchy

```text
LEFT NAV
│
├── Fleet Overview
├── Incidents
├── Reliability
├── Cohorts
├── Components
├── Firmware
├── Predictive ML
└── Root Cause
      │
      ├── Overview / hypotheses / benchmark
      ├── incident queue / vehicle investigation
      ├── Cases
      ├── Fleet Patterns
      ├── Prognostics
      ├── Automation
      ├── Fleet Decisions
      ├── Vehicle Twin
      ├── Planning
      ├── Fleet Command
      ├── Transitions
      ├── Episodes
      ├── Events
      ├── Replay
      └── Model Comparison
```

Fleet Command adds another focused navigation layer:

```text
Fleet Command
│
├── Command Center
├── Explainability
├── Decision Queue
└── Closed Loop
```

This hierarchy is intentional: the left navigation selects the product domain, the page tab selects a component/view, and Fleet Command workspaces select operator tasks.

---

# Engineering principles

1. **Explainability before complexity.** Every important operational score should be decomposable into evidence/factors.
2. **No leaked labels.** Private synthetic failure truth does not belong in normal operational telemetry.
3. **Cohort-aware analysis.** Firmware, factory, component revision, model, environment, and mileage are first-class context.
4. **Replayability.** Diagnostic state must be reproducible from run-frozen evidence.
5. **Model lineage matters.** Historical predictions are not automatically comparable across incompatible model families.
6. **Human control at action boundaries.** Recommendations may be generated automatically; approval/execution remain explicit.
7. **Idempotency at persistence boundaries.** Deterministic keys plus database uniqueness protect repeated/concurrent materialization.
8. **Workflow truth is not physical truth.** Execution metadata must not be presented as proof of repair.
9. **Inactive UI should be operationally inactive.** Hidden heavy tabs should not continue unnecessary polling.
10. **Do not solve architecture problems with larger limits first.** Reduce waste before increasing database/stream capacity.

---

# Phase 8.2 target architecture — outcome verification

The next phase adds a post-execution observation layer.

```text
EXECUTED recommendation
          │
          ▼
baseline evidence snapshot
          │
          ▼
observation window
          │
          ▼
post-execution evidence snapshot
          │
          ▼
deterministic outcome evaluator
          │
          ├── IMPROVED
          ├── STABLE
          ├── WORSENED
          ├── NO_MATERIAL_CHANGE
          └── INSUFFICIENT_DATA
```

The evaluator will compare observable evidence such as model confidence, attention score, diagnostic state, case state, and workflow coverage.

It must not turn post-workflow correlation into a repair-causality claim.

Planned persistence boundary:

```text
recommendation_id
evaluation_window/version
        ↓
deterministic outcome key
        ↓
unique persisted outcome
```

Preview and materialization will remain separate, following the same pattern as Phase 8.0 recommendations.

---

# Future platform architecture

Phase 8.3–8.5 will add effectiveness aggregation, policy replay/evaluation, and shadow-mode policy experiments.

Phase 9 will focus on production/platform concerns:

```text
FleetMind intelligence
        │
        ├── OpenTelemetry / Prometheus / Grafana
        ├── explicit SLOs
        ├── stream/backpressure/load testing
        ├── scalable historical data layer
        ├── Kubernetes / Helm deployment
        ├── model registry / promotion
        └── multi-asset reliability plugins
```

The long-term architecture should support EVs, robots, chargers, and energy systems without weakening the evidence and human-control boundaries established in the current system.

---

## Completion architecture: Phases 8.2–9.5

```text
EXECUTED HUMAN-CONTROLLED WORKFLOW
              |
              v
      Outcome Observation 8.2
      before / after evidence
              |
              v
   Effectiveness Analytics 8.3
   descriptive + evidence gates
              |
              +-------------------------+
              |                         |
              v                         v
    Policy Replay 8.4           Shadow Experiments 8.5
    frozen evidence             control vs candidate
    no recommendation writes    no production writes
              |                         |
              +------------+------------+
                           |
                           v
                    Human governance
                           |
                           v
                  FleetMind Platform 9.x
           +---------------+----------------+
           |               |                |
           v               v                v
     Observability     Model Ops       Multi-Asset
     Prom/OTel         registry        robot/charger/
     SLO targets       drift/gates     energy telemetry
           |
           v
     Deployment / Scale
     Helm + HPA/PDB
     load/backpressure/DR harnesses
     Parquet + optional Iceberg
```

### Post-execution evidence boundary

An outcome record joins an executed recommendation to observable baseline and
post-execution evidence. The evaluator may classify a change as `IMPROVED`,
`STABLE`, `WORSENED`, `NO_MATERIAL_CHANGE`, `PENDING_OBSERVATION`, or
`INSUFFICIENT_DATA`.

The classification is explicitly **not** proof that maintenance caused the
change or that a physical repair occurred.

### Policy governance boundary

Policy replay consumes a frozen fleet-decision snapshot when available.
Candidate policies can filter recommendation type, workflow priority, source
families and per-vehicle volume. Replay is no-write. A policy marked promoted
is governance metadata; the existing production recommendation generator is
not silently replaced.

Shadow experiments persist the exact replay input and both policy results so a
future review can reproduce the comparison.

### Platform observability boundary

The API exposes Prometheus metrics and optional OpenTelemetry traces. Grafana
is an optional Compose-profile service. SLO values are declared targets; no
production SLO is claimed until measured in the target environment.

### Storage and stream-scale boundary

PostgreSQL remains online state. The archive service incrementally emits
partitioned Parquet and can append to pre-created Iceberg tables when an
external catalog is configured. Kafka remains the interchange boundary for a
future Flink/Spark adoption if measured stateful-streaming requirements justify
one.

### Deployment boundary

Kubernetes deployments disable implicit application migration and use a Helm
pre-install/pre-upgrade migration Job. API and worker HPAs are available, but
horizontal scaling must be reconciled with Kafka partitions and database
capacity.

### Multi-asset boundary

Robot, charger and energy-system plugins share transparent reliability
attention primitives. Their telemetry remains observable and asset-specific.
The plugin layer does not issue actuator commands, autonomous maintenance, or
safety decisions.
