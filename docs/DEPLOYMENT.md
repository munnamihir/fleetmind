# FleetMind Deployment Engineering

Phase 9.3 ships a Helm chart under `deploy/helm/fleetmind`.

The chart assumes PostgreSQL and Kafka/Redpanda are managed separately for
staging/production. This avoids hiding database/broker durability decisions
inside an application chart.

## Render locally

```bash
helm template fleetmind deploy/helm/fleetmind \
  -f deploy/helm/fleetmind/values-dev.yaml
```

## Install staging

```bash
helm upgrade --install fleetmind deploy/helm/fleetmind \
  --namespace fleetmind \
  --create-namespace \
  -f deploy/helm/fleetmind/values-staging.yaml \
  --set database.existingSecret=fleetmind-database
```

The existing secret must contain the key `DATABASE_URL` unless `urlKey` is
changed.

## Migration discipline

Kubernetes deployments set `FLEETMIND_AUTO_MIGRATE=false`. A Helm pre-install /
pre-upgrade Job runs `python -m app.migrate` exactly once for the release.
FleetMind's compatibility migration uses a PostgreSQL advisory transaction lock,
so concurrent migration attempts remain serialized.

## Horizontal scaling

API and worker HPAs are included. Kafka partition count and database capacity
must be sized to support the selected replica counts. More pods are not a
substitute for measured capacity.

## Disaster recovery

`tools/disaster_recovery_smoke.sh` provides a local PostgreSQL backup/restore
procedure. Production RPO/RTO claims require deployment-specific backup
storage, retention, restore timing and failure exercises.
