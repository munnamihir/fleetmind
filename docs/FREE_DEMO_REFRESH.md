# FleetMind Free Demo Refresh

FleetMind's zero-cost public deployment does not run Kafka, a simulator worker, an ingestion worker, or an ML worker continuously. Instead, a bounded GitHub Actions job periodically refreshes a deterministic synthetic experiment in the Neon Free database and runs the existing diagnostic materialization pipeline.

## Cost model

The refresh uses a standard GitHub-hosted runner. The repository is public, so standard hosted-runner usage is free under GitHub's public-repository policy. The runtime requires only the existing free Render static/API services and Neon Free Postgres.

No Docker, Redpanda, paid Render worker, persistent Render disk, or continuously running trainer is required.

## Repository secret

Create this GitHub Actions repository secret:

`FLEETMIND_DEMO_DATABASE_URL`

Its value must be the same single-line Neon pooled PostgreSQL connection URL used by the Render API. Do not include `DATABASE_URL=` and do not include quotes, comments, or an `.env` block.

## Run manually

After the workflow is merged into `main`:

1. Open GitHub → FleetMind → Actions.
2. Select **FleetMind Free Demo Refresh**.
3. Choose **Run workflow** on `main`.
4. Follow the job logs until `status: complete` appears.

The workflow also runs weekly at 09:17 UTC on Monday. This low-frequency schedule keeps the free database bounded while preserving a useful public demonstration dataset.

## What the job does

1. Uses fixed experiment ID `exp-free-demo-v1`.
2. Removes prior high-volume telemetry/failure rows for that demo experiment and clears demo alerts.
3. Builds the deterministic FleetMind synthetic fleet using the existing simulator implementation.
4. Generates a bounded number of sensor samples and ground-truth failure events.
5. Persists telemetry/failures through the existing worker persistence functions directly to Neon.
6. Runs the existing diagnostic trainer without changing evidence thresholds.
7. Requires the diagnostic run to reach `trained`; otherwise the workflow fails with the readiness report.
8. Materializes extended replay, diagnostic events, episodes, and cases for that run.
9. Verifies that the trained run has persisted operational predictions.

## Interpretation boundary

The dataset is deterministic synthetic demonstration data. It is not live vehicle telemetry. Diagnostic model hypotheses remain model outputs from observable telemetry, not physical failure probabilities or direct access to simulator-private failure truth. Operational actions/workflow state remain distinct from physical repair and causal proof.

## Verification

After a successful refresh, these public endpoints should return `200`:

- `/health`
- `/api/v1/fleet/summary`
- `/api/v1/diagnostics/status`
- `/api/v1/diagnostics/fleet-command/summary`

The Fleet Command endpoint should no longer return the current `503` caused by the absence of an active experiment diagnostic run.
