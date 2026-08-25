from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def _column_exists(connection, table_name: str, column_name: str) -> bool:
    return bool(
        connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = :table_name
                      AND column_name = :column_name
                )
                """
            ),
            {
                "table_name": table_name,
                "column_name": column_name,
            },
        ).scalar()
    )


def _index_exists(connection, table_name: str, index_name: str) -> bool:
    return bool(
        connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = :table_name
                      AND indexname = :index_name
                )
                """
            ),
            {
                "table_name": table_name,
                "index_name": index_name,
            },
        ).scalar()
    )


def ensure_schema_compatibility() -> None:
    """
    Apply FleetMind additive compatibility migrations safely.

    Multiple services can start concurrently. A PostgreSQL advisory
    transaction lock ensures only one service performs migration checks
    at a time.
    """

    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(68106101)")
        )

        if not _column_exists(
            connection,
            "telemetry",
            "experiment_id",
        ):
            connection.execute(
                text(
                    """
                    ALTER TABLE telemetry
                    ADD COLUMN experiment_id VARCHAR(64)
                    """
                )
            )

        if not _column_exists(
            connection,
            "failure_events",
            "experiment_id",
        ):
            connection.execute(
                text(
                    """
                    ALTER TABLE failure_events
                    ADD COLUMN experiment_id VARCHAR(64)
                    """
                )
            )

        if not _index_exists(
            connection,
            "telemetry",
            "ix_telemetry_experiment_id",
        ):
            connection.execute(
                text(
                    """
                    CREATE INDEX ix_telemetry_experiment_id
                    ON telemetry (experiment_id)
                    """
                )
            )

        if not _index_exists(
            connection,
            "failure_events",
            "ix_failure_events_experiment_id",
        ):
            connection.execute(
                text(
                    """
                    CREATE INDEX ix_failure_events_experiment_id
                    ON failure_events (experiment_id)
                    """
                )
            )
