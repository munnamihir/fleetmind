# FleetMind Zero-Cost Public Cloud

This deployment profile keeps the public FleetMind demo at $0/month within provider free-tier limits.

## Runtime architecture

- Render Static Site: FleetMind web console
- Render Free Web Service: FastAPI
- Neon Free Postgres: persistent database
- GitHub Actions: scheduled/batch refresh and ML maintenance for the public demo

The production streaming implementation remains in source control, including Redpanda/Kafka, worker, simulator, ML trainer, Docker Compose, and Kubernetes manifests. Those services are not provisioned by the zero-cost public deployment.

## Why Redpanda is not part of the permanent free deployment

Redpanda Cloud Serverless offers trial credits, not a permanent free tier. A permanently running Kafka-compatible broker plus continuously running consumer/simulator/trainer processes therefore cannot be guaranteed at $0/month.

The public demo substitutes scheduled batch refreshes for continuous streaming. This changes execution cadence, not FleetMind's truth boundaries: correlation is not causality, attention is not physical failure probability, workflow execution is not physical repair, and human approval remains mandatory.

## Render

`render.yaml` provisions only:

1. `fleetmind-munnamihir` — static site
2. `fleetmind-api-munnamihir` — Python web service on Render's Free plan

The API `DATABASE_URL` is `sync: false` and must be supplied from Neon during Blueprint creation.

Free Render web services can sleep after inactivity. The first request after a sleep can take longer while the service wakes.

## Neon

Create a free Neon Postgres project and copy its pooled connection string. Store it only as the Render `DATABASE_URL` secret and, when scheduled refresh jobs are enabled, as a GitHub Actions repository secret.

FleetMind normalizes ordinary `postgresql://` provider URLs to SQLAlchemy's psycopg 3 URL form automatically.

## Public URLs

Expected web console:

`https://fleetmind-munnamihir.onrender.com`

Expected API:

`https://fleetmind-api-munnamihir.onrender.com`

The static site proxies `/api/*` and `/health` to the API so the browser does not use localhost.

## Cost guardrails

The zero-cost Blueprint intentionally contains none of the following:

- Render background workers
- Render paid compute plans
- Render managed Postgres
- Render persistent disks
- Redpanda Cloud credentials
- Kafka bootstrap configuration

If any of those are reintroduced into `render.yaml`, review provider pricing before deployment.

## Validation

```bash
PYTHONPATH="$PWD/services/common:$PWD/services/ml" \
python -m unittest discover -s tests -p "test_cloud_runtime_contract.py" -v

PYTHONPATH="$PWD/services/common:$PWD/services/ml" \
python -m unittest discover -s tests -v

cd web
npm install
npm run build
```

## Free-tier limitations

This profile is intended for a portfolio/demo/research deployment rather than a production SLA. Free services can impose sleep, compute, storage, bandwidth, and execution limits. Keep FleetMind demo datasets compact and refresh them in bounded batches.
