# Stream Processing Decision Record

## Decision

FleetMind Phase 9.2 does **not** add Spark or Flink merely to satisfy a roadmap
checkbox. The existing worker already performs Kafka batch ingestion and the
diagnostic/model layers are run-frozen offline computations.

A dedicated stateful stream processor becomes justified when FleetMind needs
one or more of the following at production scale:

- event-time joins across independent asset streams;
- long-lived keyed state beyond the current worker's responsibilities;
- exactly-once stream-to-stream transforms;
- windowed aggregations that cannot reasonably be persisted and computed from
  PostgreSQL/Parquet;
- sustained throughput where measured worker/database bottlenecks remain after
  batching, partitioning and horizontal consumers.

## Adapter boundary

Kafka topics remain the interchange boundary. The Phase 9.2 load harness,
consumer-lag tests and Parquet/Iceberg archive provide the evidence needed to
decide whether the next production deployment should introduce Flink, Spark
Structured Streaming, or neither.

## Claim boundary

"Stream processor evaluated" means FleetMind has an explicit adoption decision
and interface boundary. It does not mean unused Spark/Flink infrastructure was
added to the local demo.
