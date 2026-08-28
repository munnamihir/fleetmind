# Historical Storage and Retention

The optional `archive` service writes incremental PostgreSQL telemetry to
partitioned Zstandard-compressed Parquet:

```text
/archive/
  telemetry/experiment_id=<id>/date=<yyyy-mm-dd>/part-*.parquet
  asset_telemetry/experiment_id=<id>/date=<yyyy-mm-dd>/part-*.parquet
  manifest.json
```

The manifest stores database watermarks and emitted file metadata. The service
therefore resumes after restart without blindly exporting the entire database.

`ARCHIVE_RETENTION_DAYS` controls local Parquet retention. The default is 30
days.

If `ICEBERG_CATALOG_URI` is configured, the service attempts to append Arrow
tables to existing Iceberg tables named:

- `fleetmind.telemetry`
- `fleetmind.asset_telemetry`

FleetMind intentionally does not create an external catalog or production
warehouse implicitly. Catalog creation, credentials and table lifecycle belong
to deployment-specific infrastructure.
