# FleetMind Build Roadmap

This roadmap reflects the repository state after **Phase 8.1** and the nested-dashboard active-polling hardening.

Status legend:

- ✅ complete / implemented
- 🚧 next or actively planned
- ⏳ future
- 🧪 intentionally experimental / bounded claim

---

## Phase 1 — Live Reliability Console ✅

- [x] Synthetic EV fleet generator
- [x] Hidden coolant-pump degradation scenario
- [x] Redpanda/Kafka telemetry stream
- [x] Explainable anomaly/risk worker
- [x] PostgreSQL persistence
- [x] FastAPI fleet endpoints
- [x] Live React engineering dashboard
- [x] Component-revision cohort view
- [x] Containerized local stack
- [x] Experiment identity support

## Phase 2 — Reliability Science ✅

- [x] Private failure/event truth side channel for evaluation only
- [x] Right-censored Weibull estimation by component cohort
- [x] Kaplan-Meier survival curves
- [x] B10/B50 / characteristic-life estimates
- [x] Early-warning detection rate
- [x] Lead mileage / accelerated-time metrics
- [x] Reliability engineering dashboard
- [x] Failure drill-down

### Deferred research

- [ ] Physical remaining-useful-life model with independently justified target
- [ ] Additional reliability estimators beyond the current Weibull/KM baseline

## Phase 3 — Firmware Regression Lab ✅

- [x] Matched treatment/control cohorts
- [x] Coarsened exact matching / stratification
- [x] Statistical significance and effect-size reporting
- [x] Regression classification
- [x] Hardware × firmware interaction analysis
- [x] Firmware regression engineering dashboard

### Future extensions

- [ ] Pre/post rollout timeline comparisons
- [ ] Rollout adoption visualization
- [ ] Multi-release regression history

## Phase 4 / 5 — Predictive Maintenance ML ✅

### Feature and label discipline

- [x] Rolling telemetry feature windows
- [x] Leakage guard
- [x] Prospective failure-horizon labels
- [x] Right-censored negative handling
- [x] Simulator reset / mileage epoch guard
- [x] Failure truth epoch/timestamp continuity guard
- [x] Minimum pre-failure observation warm-up
- [x] Duplicate failure suppression

### Model development

- [x] Sensor-only XGBoost classifier
- [x] Logistic-regression baseline
- [x] Vehicle-isolated development split
- [x] Group-stratified validation inside development data
- [x] Validation-derived operational threshold
- [x] Optional Platt calibration when evidence supports it

### Benchmark integrity

- [x] Deterministic label-agnostic frozen benchmark vehicle cohort
- [x] Benchmark evidence qualification gate
- [x] Operational scoring separated from benchmark claims
- [x] Exact locked benchmark snapshot after qualification
- [x] SHA-256 dataset integrity
- [x] Feature-schema integrity hash
- [x] Fail-closed benchmark artifact verification
- [x] Explicit model-lineage boundary

### Evaluation and UI

- [x] ROC-AUC / PR-AUC
- [x] Precision / recall / F1
- [x] Brier score
- [x] Confusion matrix
- [x] Calibration view
- [x] ML early-warning lead-distance metric
- [x] Persisted model runs
- [x] Live predictions
- [x] Longitudinal same-lineage prediction history
- [x] Predictive Maintenance ML dashboard

### Future ML extensions

- [ ] Survival/RUL model with a defensible target
- [ ] Time-series model benchmark
- [ ] MLflow experiment tracking
- [ ] External model registry / promotion workflow

---

# Diagnostic intelligence program

## Phase 6 — Root Cause & Diagnostic Workflow ✅

The original Root Cause and Incident Replay milestones have been implemented as a broader diagnostic-intelligence stack.

### Events, transitions, episodes, replay

- [x] Diagnostic event generation
- [x] Anti-chatter event behavior
- [x] Diagnostic transitions
- [x] Temporal diagnostic episodes
- [x] Replay
- [x] Extended replay
- [x] Run pinning / reproducibility
- [x] Root Cause dashboard

### Cases and investigation workflow

- [x] Diagnostic case materialization
- [x] Case workflow state
- [x] Case summary and search
- [x] Vehicle investigation detail
- [x] Evidence traces
- [x] Watchlists
- [x] Saved investigation views

### Fleet pattern intelligence

- [x] Cohort/pattern hotspot views
- [x] Cross-case clustering
- [x] Similar-case lookup
- [x] Firmware/factory/revision/model/hypothesis dimensions

### Prognostics and maintenance

- [x] Run-frozen hypothesis trajectories
- [x] Experimental threshold-horizon estimation
- [x] Prognostic maintenance queue
- [x] Horizon backtest against later model-threshold crossing
- [x] Operator maintenance planning
- [x] Maintenance activity history
- [x] Explicit truth boundary: not physical RUL

### Operational automation

- [x] Deterministic source-versioned automation policies
- [x] Dry-run simulation
- [x] Approval queue
- [x] Explicit approve / reject / execute workflow
- [x] Non-destructive workflow effects only
- [x] Immutable action audit trail
- [x] No automatic physical action

---

# Fleet operational intelligence program

## Phase 7 — Fleet Intelligence & Digital Operations ✅

### Vehicle operational twin

- [x] Unified vehicle operational state
- [x] Model / diagnostic / case / prognostic / maintenance / automation layers
- [x] Coverage state
- [x] Longitudinal timeline
- [x] State lineage graph
- [x] Evidence inventory
- [x] Twin checkpoints
- [x] Twin comparison
- [x] Explicit boundary: operational twin, not physics twin

### Fleet decision intelligence

- [x] Deterministic fleet decision states
- [x] Attention score
- [x] Synthetic workflow load units
- [x] Coverage debt
- [x] Decision queue
- [x] Cohort concentration
- [x] No-write workflow scenario lab
- [x] Fleet decision checkpoints
- [x] Explicit boundary: attention is not physical risk

### Fleet planning and change intelligence

- [x] Capacity-planning rules
- [x] Fleet change snapshots
- [x] Fleet-twin summary/cohort views
- [x] Workflow-effectiveness summary and policies

### Fleet Command foundation

- [x] Fleet Command Center
- [x] Operator queue summaries
- [x] Cohort analysis
- [x] Deterministic attention-factor explanation
- [x] Evidence explainability
- [x] Evidence lineage
- [x] Decision Queue
- [x] Selected-vehicle drill-through

---

# Closed-loop operations program

## Phase 8.0 — Closed-Loop Operations Foundation ✅

- [x] Deterministic recommendation candidate generation
- [x] Preview evaluation without persistence
- [x] Explicit persistent materialization
- [x] Selected-vehicle-only materialization
- [x] Deterministic recommendation key
- [x] Database uniqueness for recommendation keys
- [x] Normal-request idempotency
- [x] Concurrent insert race handling with savepoint
- [x] Concurrent winner reload instead of duplicate 500
- [x] Atomic recommendation + CREATED audit activity
- [x] No automatic approval
- [x] No automatic execution
- [x] No physical action

## Phase 8.1 — Ownership, Decision Queue & Lifecycle ✅

- [x] Recommendation ownership (`assigned_to`, `assigned_at`)
- [x] Decision Queue summary
- [x] Active queue
- [x] Ownership views
- [x] Workflow-status views
- [x] Operator assignment / unassignment
- [x] Acknowledge transition
- [x] Request-approval transition
- [x] Approve transition
- [x] Mark execution-ready transition
- [x] Explicit execute-workflow transition
- [x] Audit activity and last-actor tracking
- [x] Human approval gate remains mandatory

### Phase 8.1 UI / runtime hardening ✅

- [x] Internal tabs across Fleet Overview
- [x] Internal tabs across Incidents
- [x] Internal tabs across Reliability
- [x] Internal tabs across Cohorts
- [x] Internal tabs across Components
- [x] Internal tabs across Firmware
- [x] Internal tabs across Predictive ML
- [x] Internal tabs across Root Cause
- [x] Fleet Command nested workspace tabs
- [x] Page-level active polling
- [x] Heavy Root Cause modules lazy-mounted by active tab
- [x] Fleet Command active-workspace polling
- [x] React Strict Mode retained
- [x] SQLAlchemy QueuePool fan-out fixed without increasing pool size

---

# Future ahead

## Phase 8.2 — Closed-Loop Outcome Verification 🚧 NEXT

Goal: answer **“what observable evidence changed after an executed workflow recommendation?”**

Planned:

- [ ] Persisted recommendation outcome record
- [ ] Baseline snapshot at/around workflow execution
- [ ] Post-execution observation snapshot
- [ ] Deterministic pre/post delta evaluator
- [ ] Outcome states such as:
  - `PENDING_OBSERVATION`
  - `INSUFFICIENT_DATA`
  - `IMPROVED`
  - `STABLE`
  - `WORSENED`
  - `NO_MATERIAL_CHANGE`
- [ ] Evaluation-version field
- [ ] Idempotent outcome materialization
- [ ] Database uniqueness for outcome evaluation keys
- [ ] Preview vs materialize API
- [ ] Outcome summary API
- [ ] Outcome detail API
- [ ] Fleet Command **Outcomes** tab
- [ ] Before/after evidence comparison UI
- [ ] Contract/math/concurrency tests
- [ ] Explicit claim boundary: observed change does not prove repair causality

## Phase 8.3 — Closed-Loop Effectiveness Analytics ⏳

Goal: aggregate observed workflow outcomes without overstating physical effect.

Planned:

- [ ] Outcome distributions by recommendation type
- [ ] Outcome distributions by fleet cohort
- [ ] Time-to-observation metrics
- [ ] Recommendation-to-workflow completion funnel
- [ ] Assignment / approval latency
- [ ] Repeated recommendation analysis
- [ ] Coverage-gap closure analysis
- [ ] Operator/workflow effectiveness metrics
- [ ] Comparison windows with minimum-evidence gates
- [ ] No causal “maintenance success rate” claim without a valid design

## Phase 8.4 — Recommendation Policy Evaluation ⏳

Goal: measure recommendation policy quality before changing production behavior.

Planned:

- [ ] Versioned recommendation policies
- [ ] Policy replay against historical run-frozen evidence
- [ ] Candidate volume / selectivity metrics
- [ ] Conflict detection
- [ ] Duplicate recommendation suppression
- [ ] Policy cohort coverage
- [ ] Policy explainability
- [ ] Promotion criteria

## Phase 8.5 — Shadow-Mode Policy Experimentation ⏳

Goal: compare candidate policies without exposing operators to uncontrolled automatic actions.

Planned:

- [ ] Shadow policy execution
- [ ] Control vs candidate policy comparison
- [ ] No-write recommendation generation
- [ ] Versioned experiment identity
- [ ] Frozen evaluation inputs
- [ ] Outcome comparison when eligible evidence exists
- [ ] Operator review before promotion
- [ ] Rollback / disable controls

---

# Phase 9.0 — Fleet Reliability Intelligence Platform ⏳

Phase 9 shifts FleetMind from a feature-rich local engineering demo toward a scalable reliability platform.

## 9.1 Platform observability

- [ ] OpenTelemetry instrumentation
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] API latency/error metrics
- [ ] Database pool utilization metrics
- [ ] Polling/request fan-out monitoring
- [ ] SLO definitions

## 9.2 Stream and storage scale

- [ ] Load generator to 100K+ events/sec
- [ ] Backpressure tests
- [ ] Broker failure / replay tests
- [ ] Stream processor evaluation (Flink/Spark only where justified)
- [ ] Parquet/Iceberg historical data layer
- [ ] Retention / compaction strategy

## 9.3 Deployment engineering

- [ ] Kubernetes manifests
- [ ] Helm packaging
- [ ] Environment-separated configuration
- [ ] Secrets strategy
- [ ] Migration discipline
- [ ] Horizontal API/worker scaling
- [ ] Disaster/recovery tests

## 9.4 Model operations

- [ ] External model registry
- [ ] Model promotion workflow
- [ ] Feature/schema compatibility gates
- [ ] Drift monitoring
- [ ] Benchmark lineage governance
- [ ] Reproducible offline evaluation jobs

## 9.5 Physical AI / multi-asset expansion

- [ ] Robot telemetry schema
- [ ] Actuator current / temperature / torque simulator
- [ ] Gearbox/vibration degradation scenario
- [ ] Charger/energy-system reliability schema
- [ ] Shared reliability primitives across EV and robot assets
- [ ] Asset-specific diagnostic plugins

---

## Long-term design rule

FleetMind should evolve from:

```text
telemetry → detection → diagnosis
```

into:

```text
telemetry
   ↓
detection
   ↓
evidence
   ↓
diagnosis
   ↓
fleet decision
   ↓
human-approved workflow
   ↓
observed outcome
   ↓
policy learning
```

without silently crossing these boundaries:

```text
correlation ≠ causality
attention ≠ physical risk probability
model-confidence horizon ≠ physical RUL
workflow execution ≠ physical repair
observed improvement ≠ proof that maintenance caused improvement
```
