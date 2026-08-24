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

- [ ] Failure/event ground-truth side channel for offline evaluation only
- [ ] Weibull shape/scale estimation by component cohort
- [x] Kaplan-Meier survival curves
- [ ] Mean/median remaining useful life
- [ ] Early-warning lead-time metric
- [ ] False-positive and missed-failure evaluation

## Milestone 3 — Firmware Regression Lab

- [ ] Matched treatment/control cohorts
- [ ] Pre/post firmware comparisons
- [ ] Propensity matching or stratification
- [ ] Statistical significance and effect size
- [ ] Automated regression alert
- [ ] Rollout adoption visualization

## Milestone 4 — Predictive Maintenance ML

- [ ] Feature store
- [ ] XGBoost failure classifier baseline
- [ ] Survival/RUL model
- [ ] Time-series model benchmark
- [ ] MLflow experiment tracking
- [ ] Model registry and versioned inference

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
