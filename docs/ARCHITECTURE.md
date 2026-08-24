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
