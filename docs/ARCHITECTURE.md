# FleetMind Architecture

## Phase 1 data path

```text
Synthetic EV Fleet
      │
      │ JSON telemetry
      ▼
Redpanda / Kafka
      │
      ▼
Anomaly Worker ───────────────┐
      │                       │
      │ explainable risk      │ alerts
      ▼                       ▼
PostgreSQL               PostgreSQL
      │                       │
      └──────────┬────────────┘
                 ▼
             FastAPI
                 │
                 ▼
      React Engineering Console
```

## Why this architecture

The first milestone separates generation, transport, analytics, persistence, API, and UI so each layer can evolve independently. Kafka-compatible Redpanda makes telemetry replayable and allows future workers for Weibull analysis, feature extraction, firmware experiments, and RUL prediction to subscribe without coupling them to ingestion.

## Event contract

Telemetry deliberately contains observable engineering measurements and deployment metadata, not a `failed` or `is_degraded` label. The simulator maintains latent degradation internally and lets the analytics layer infer it.

Key fields:

- Vehicle: ID, model, factory, firmware, mileage, component revision.
- Environment: ambient temperature and speed.
- Battery: SOC, voltage, current, temperature, cell imbalance.
- Powertrain: motor/inverter temperatures and motor RPM.
- Thermal loop: coolant temperature, coolant-pump RPM and current.

## Phase 2 target architecture

```text
                         ┌─────────────────────────────┐
                         │         FleetMind           │
                         └─────────────────────────────┘
                                      │
Vehicle / Robot / Charger telemetry ──┼──► Kafka
                                      │
             ┌────────────────────────┼────────────────────────┐
             ▼                        ▼                        ▼
       Stream features          Raw Data Lake            Online state
       Spark / Flink          Parquet + Iceberg           Redis/PG
             │                        │                        │
             ├───────────────┬────────┴─────────────┐          │
             ▼               ▼                      ▼          ▼
       Anomaly models    Reliability engine      RUL model   API
             │          Weibull / survival          │          │
             └───────────────┬──────────────────────┘          │
                             ▼                                 │
                     Root-cause graph ◄────────────────────────┘
                             │
                             ▼
                    Engineering Console
```

## Engineering principles

1. **Explainability before complexity.** V1 uses transparent signals so every alert can show evidence.
2. **No leaked labels.** Failure state is not included in production telemetry messages.
3. **Cohort-aware analysis.** Firmware, factory, component revision, environment and mileage are first-class dimensions.
4. **Replayability.** Incidents should be reproducible from the event log.
5. **Model-agnostic platform.** The platform should accept rules, classical ML, time-series models and survival analysis behind stable interfaces.

## Predictive ML benchmark boundary (Phase 5.1)

FleetMind separates model development from benchmark claims at the vehicle boundary:

```text
eligible causal windows
        |
        +-- development train vehicles ---> model fit
        |
        +-- development validation vehicles ---> calibration + threshold
        |
        `-- frozen benchmark vehicles ---> evaluation only
```

Frozen benchmark membership is a deterministic SHA-256 bucket of `vehicle_id` with a fixed seed. It does not depend on labels, failure status, firmware, component revision, or model results, so a vehicle cannot migrate between development and benchmark as new failure truth arrives.

Operational scoring is separate: after a complete run, the selected XGBoost model scores the latest causal window for every active vehicle. A benchmark can be marked `insufficient_evidence` while operational scoring continues. Headline benchmark claims require at least 1,000 benchmark windows, 20 positive windows, 8 distinct failure vehicles, and both outcome classes.

Every run also fits a logistic-regression baseline using the identical sensor features and cohorts. XGBoost is therefore compared against a simple model instead of against no baseline. Historical live predictions are retained by model run and exposed as a per-vehicle longitudinal risk series.
