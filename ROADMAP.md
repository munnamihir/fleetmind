# FleetMind Build Roadmap

## Milestone 1 — Live Reliability Console ✅

- [x] Synthetic EV fleet generator
- [x] Hidden CP-17 coolant-pump degradation scenario
- [x] Redpanda/Kafka telemetry stream
- [x] Explainable anomaly/risk worker
- [x] PostgreSQL persistence
- [x] FastAPI fleet endpoints
- [x] Live React engineering dashboard
- [x] Component-revision cohort view
- [x] Containerized local stack

## Milestone 2 — Reliability Science

- [x] Failure/event ground-truth side channel for offline evaluation only
- [x] Weibull shape/scale estimation by component cohort
- [x] Kaplan-Meier survival curves
- [ ] Mean/median remaining useful life
- [x] Early-warning lead-time metric
- [ ] False-positive and missed-failure evaluation
- [x] Reliability engineering dashboard

## Milestone 3 — Firmware Regression Lab

- [x] Matched treatment/control cohorts
- [ ] Pre/post rollout timeline comparisons
- [x] Coarsened exact matching / stratification
- [x] Statistical significance and effect size
- [x] Automated regression classification
- [x] Hardware × firmware interaction analysis
- [x] Firmware regression engineering dashboard
- [ ] Rollout adoption visualization

## Milestone 4 — Predictive Maintenance ML

- [x] Rolling telemetry feature windows with leakage guard
- [x] Right-censored future-horizon labeling
- [x] Frozen vehicle-level benchmark + validation/development separation
- [x] XGBoost failure classifier
- [x] Validation-derived operational threshold
- [x] Probability calibration framework
- [x] ROC-AUC / PR-AUC / precision / recall / F1 / Brier evaluation
- [x] ML early-warning lead-distance metric
- [x] Persisted model runs and live vehicle predictions
- [x] Logistic-regression baseline on identical features/cohorts
- [x] Benchmark evidence qualification gate
- [x] Operational scoring vs benchmark-claim separation
- [x] Longitudinal per-vehicle prediction history
- [x] Model-lineage-aware history isolation
- [x] Simulator mileage-reset / experiment-epoch guard
- [x] Failure-truth epoch/timestamp continuity guard
- [x] Automatic exact benchmark snapshot lock after qualification
- [x] SHA-256 + feature-schema integrity verification for locked benchmark
- [x] Group-stratified development validation with frozen benchmark membership
- [x] Minimum 3,000-mile failure-observation warm-up for causal ML windows
- [x] Duplicate failure-event suppression at identical failure mileage
- [x] Predictive Maintenance ML dashboard
- [ ] Survival/RUL model
- [ ] Time-series model benchmark
- [ ] MLflow experiment tracking
- [ ] External model registry / promotion workflow

## Milestone 5 — Root Cause Intelligence

- [ ] Automatic failure clustering
- [ ] Cohort enrichment across firmware/factory/revision/climate/mileage
- [ ] Correlation graph
- [ ] Root-cause hypothesis ranking
- [ ] Evidence trace for every hypothesis

## Milestone 6 — Incident Replay

- [ ] Timeline scrubber
- [ ] Telemetry channels synchronized around alert/failure
- [ ] Compare affected vehicle against matched healthy fleet
- [ ] Export an incident packet

## Milestone 7 — Physical AI / Optimus Mode

- [ ] Robot telemetry schema
- [ ] Actuator current/temperature/torque simulator
- [ ] Gearbox vibration degradation
- [ ] Robot service diagnostics dashboard
- [ ] Shared reliability primitives across EV and robot assets

## Milestone 8 — Scale & Production Engineering

- [ ] Spark/Flink stream processing
- [ ] Parquet + Iceberg data lake
- [ ] OpenTelemetry instrumentation
- [ ] Prometheus/Grafana
- [ ] Kubernetes manifests / Helm
- [ ] Load generator to 100K+ events/sec
- [ ] Backpressure/failure/replay tests
- [ ] SLO dashboard
