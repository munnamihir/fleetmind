# FleetMind SLO Definitions

Phase 9.1 introduces measurable service-level objectives. These values are
**targets**, not claims that a development laptop or future production
environment already achieves them.

| Objective | Target | Window | Indicator |
| --- | ---: | --- | --- |
| API availability | 99.5% | 30 days | non-5xx responses / all responses |
| API p95 latency | < 750 ms | 24 hours | Prometheus HTTP latency histogram |
| DB pool saturation | < 80% | 5 minutes | checked-out / available connections |
| Ingestion freshness | < 30 seconds | 5 minutes | age of latest persisted telemetry |

The `/metrics` endpoint exposes API and SQLAlchemy pool metrics. Redpanda is
scraped through its native Prometheus endpoint. Grafana provisioning ships with
a FleetMind Platform dashboard.

Do not promote an SLO target into an achieved-SLO claim until the relevant
environment has enough measured history.
