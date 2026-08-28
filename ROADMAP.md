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

# Roadmap implementation delivery

The remaining roadmap has now been delivered as one cohesive implementation
pass. The checkboxes below distinguish **implemented capability** from
**environment-dependent proof**. FleetMind never marks a throughput, SLO,
disaster-recovery or causal-maintenance claim complete merely because code for
measuring it exists.

## Phase 8.2 — Closed-Loop Outcome Verification ✅ implementation

- [x] Persisted recommendation outcome records
- [x] Baseline evidence snapshot
- [x] Post-execution evidence snapshot
- [x] Deterministic observed-outcome evaluator
- [x] `PENDING_OBSERVATION`
- [x] `INSUFFICIENT_DATA`
- [x] `IMPROVED`
- [x] `STABLE`
- [x] `WORSENED`
- [x] `NO_MATERIAL_CHANGE`
- [x] Versioned, idempotent evaluation identity
- [x] Database uniqueness
- [x] Concurrent insert winner reload
- [x] Preview vs explicit materialization
- [x] Summary/list/detail APIs
- [x] Fleet Command Outcomes view
- [x] Latest same-lineage diagnostic evidence for post-execution comparison
- [x] Explicit non-causality truth boundary

## Phase 8.3 — Closed-Loop Effectiveness Analytics ✅ implementation

- [x] Outcome distribution by recommendation type
- [x] Cohort outcome views
- [x] Materialized → assigned → acknowledged → approved → executed funnel
- [x] Assignment / approval / execution latency
- [x] Execution-to-observation latency
- [x] Repeated recommendation detection
- [x] Coverage-gap closure summary
- [x] Minimum evidence gates for grouped outcome distributions
- [x] Descriptive analytics only; no causal maintenance success rate

## Phase 8.4 — Recommendation Policy Evaluation ✅ implementation

- [x] Versioned policy entities
- [x] Immutable policy key/version identity
- [x] Frozen fleet decision snapshots as preferred replay evidence
- [x] Explicit partial/non-frozen fallback that blocks promotion
- [x] Candidate volume / selectivity
- [x] Duplicate suppression
- [x] Conflict detection
- [x] Cohort coverage
- [x] Explainable policy filters
- [x] Promotion criteria
- [x] Explicit operator promotion / disable / rollback metadata
- [x] Promotion remains control-plane metadata until separately adopted by production recommendation generation

## Phase 8.5 — Shadow-Mode Policy Experimentation ✅ implementation

- [x] Control vs candidate policy replay
- [x] No-write recommendation generation
- [x] Same frozen input for both policies
- [x] Versioned deterministic experiment identity
- [x] Overlap / control-only / candidate-only comparison
- [x] Candidate-volume delta
- [x] Conflict comparison
- [x] Observed-outcome context by recommendation type
- [x] Persistent frozen experiment input/result record
- [x] No automatic promotion or execution

---

# Phase 9 — Fleet Reliability Intelligence Platform

## Phase 9.1 — Platform Observability ✅ implementation

- [x] Prometheus API request metrics
- [x] Request latency histogram
- [x] 5xx error counter
- [x] Active-request gauge
- [x] SQLAlchemy pool checked-out / size / overflow gauges
- [x] Redpanda Prometheus scrape configuration
- [x] Grafana provisioning and FleetMind Platform dashboard
- [x] Optional OpenTelemetry FastAPI instrumentation
- [x] Explicit SLO target definitions
- [ ] Production SLO achievement over the declared measurement windows — **requires environment evidence**

## Phase 9.2 — Stream & Storage Scale ✅ implementation / validation harness

- [x] Configurable Kafka target-rate load generator
- [x] 100K-events/sec target mode
- [x] Delivered-rate measurement instead of hard-coded success claim
- [x] Backpressure / stopped-consumer backlog test
- [x] Consumer replay / lag convergence test
- [x] Broker restart smoke test
- [x] Partition-aware multi-asset topic
- [x] Stream-processor adoption decision record
- [x] Incremental Parquet archival
- [x] Zstandard compression
- [x] Experiment/date partitioning
- [x] Watermark manifest
- [x] Configurable retention
- [x] Optional Iceberg append adapter
- [ ] Sustained end-to-end 100K+ events/sec verified on a named environment — **run the harness**
- [ ] Production broker-failure/backpressure envelope characterized — **run deployment-specific tests**

## Phase 9.3 — Deployment Engineering ✅ implementation / validation harness

- [x] Helm chart
- [x] Development / staging / production values
- [x] Secret-aware database configuration
- [x] Pre-install / pre-upgrade migration Job
- [x] `FLEETMIND_AUTO_MIGRATE=false` deployment discipline
- [x] API readiness/liveness probes
- [x] API HPA
- [x] Worker HPA
- [x] API/worker PodDisruptionBudgets
- [x] Optional archive and multi-asset deployments
- [x] Local PostgreSQL backup/restore smoke test
- [ ] Production RPO/RTO verified — **requires deployment-specific recovery exercise**
- [ ] Production multi-zone broker/database architecture selected — **environment decision**

## Phase 9.4 — Model Operations ✅ implementation

- [x] Versioned model registry
- [x] Candidate / staging / production / archived stages
- [x] Artifact SHA-256 identity
- [x] Feature-schema compatibility gate
- [x] Locked benchmark snapshot identity gate
- [x] Explicit human promotion
- [x] Previous production version archival
- [x] Feature-distribution baseline
- [x] Current-vs-baseline drift report
- [x] Reproducible offline diagnostic evaluation script
- [x] Benchmark artifact SHA verification tool
- [x] Generic external registry HTTP integration via `MODEL_REGISTRY_URL`
- [ ] A specific external provider integration certified — **configure and validate the selected provider**

## Phase 9.5 — Physical AI / Multi-Asset Expansion ✅ reliability layer

- [x] Shared plugin-based reliability primitives
- [x] Robot telemetry contract
- [x] Actuator current / temperature / torque
- [x] Gearbox vibration / temperature
- [x] Robot latent degradation simulator
- [x] Charger telemetry contract and simulator
- [x] Energy-system telemetry contract and simulator
- [x] Kafka multi-asset ingestion worker
- [x] Idempotent asset event persistence
- [x] Asset summary/detail APIs
- [x] Multi-asset Platform console
- [x] Explicit boundary: operational attention, not calibrated physical failure probability
- [x] Explicit boundary: no autonomous physical control or safety decision

---

# Completion definition

The FleetMind roadmap is now implemented through Phase 9.5 at the code,
interface, test-harness and deployment-tooling level.

The following remain intentionally evidence-dependent rather than marked as
completed facts:

1. sustained throughput on a named hardware/deployment environment;
2. production SLO attainment over the defined time windows;
3. production RPO/RTO;
4. external provider-specific model-registry certification;
5. any claim that a workflow caused a physical repair, prevented a failure, or
   improved physical safety.

Those are validation programs, not missing software phases.
