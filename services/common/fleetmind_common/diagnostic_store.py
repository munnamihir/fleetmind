from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class DiagnosticModelRun(Base):
    __tablename__ = "diagnostic_model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    lineage: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(48), index=True)
    champion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    feature_schema_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    development_status: Mapped[str] = mapped_column(String(48), default="unknown")
    benchmark_status: Mapped[str] = mapped_column(String(48), default="unknown", index=True)
    snapshot_status: Mapped[str] = mapped_column(String(48), default="unknown", index=True)
    bundle_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        Index(
            "ix_diagnostic_runs_experiment_created",
            "experiment_id",
            "created_at",
        ),
        Index(
            "ix_diagnostic_runs_lineage_experiment",
            "lineage",
            "experiment_id",
        ),
    )


class DiagnosticPrediction(Base):
    __tablename__ = "diagnostic_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    anchor_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    anchor_mileage: Mapped[float] = mapped_column(Float)
    top_class: Mapped[str] = mapped_column(String(64), index=True)
    top_confidence: Mapped[float] = mapped_column(Float, index=True)
    hypotheses_json: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "vehicle_id",
            name="uq_diagnostic_prediction_run_vehicle",
        ),
        Index(
            "ix_diagnostic_prediction_run_class_confidence",
            "run_id",
            "top_class",
            "top_confidence",
        ),
        Index(
            "ix_diagnostic_prediction_experiment_vehicle",
            "experiment_id",
            "vehicle_id",
        ),
    )


class DiagnosticReplayPoint(Base):
    __tablename__ = "diagnostic_replay_points"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    anchor_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    anchor_mileage: Mapped[float] = mapped_column(Float)
    top_class: Mapped[str] = mapped_column(String(64), index=True)
    top_confidence: Mapped[float] = mapped_column(Float, index=True)
    hypotheses_json: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "vehicle_id",
            "anchor_timestamp",
            name="uq_diagnostic_replay_run_vehicle_anchor",
        ),
        Index(
            "ix_diagnostic_replay_run_vehicle_mileage",
            "run_id",
            "vehicle_id",
            "anchor_mileage",
        ),
        Index(
            "ix_diagnostic_replay_experiment_vehicle",
            "experiment_id",
            "vehicle_id",
        ),
    )


class DiagnosticEvent(Base):
    __tablename__ = "diagnostic_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    rules_version: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    anchor_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    anchor_mileage: Mapped[float] = mapped_column(Float)
    previous_class: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    current_class: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    previous_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    current_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        index=True,
    )
    confidence_delta: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    slope_per_1k_miles: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    details_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "vehicle_id",
            "event_type",
            "anchor_timestamp",
            name="uq_diagnostic_event_run_vehicle_type_anchor",
        ),
        Index(
            "ix_diagnostic_event_run_type_timestamp",
            "run_id",
            "event_type",
            "anchor_timestamp",
        ),
        Index(
            "ix_diagnostic_event_run_vehicle_mileage",
            "run_id",
            "vehicle_id",
            "anchor_mileage",
        ),
        Index(
            "ix_diagnostic_event_experiment_vehicle",
            "experiment_id",
            "vehicle_id",
        ),
    )


class DiagnosticEpisode(Base):
    __tablename__ = "diagnostic_episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    rules_version: Mapped[str] = mapped_column(String(64), index=True)
    source_event_rules_version: Mapped[str] = mapped_column(String(64), index=True)
    hypothesis_class: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    start_reason: Mapped[str] = mapped_column(String(48), index=True)
    start_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    start_mileage: Mapped[float] = mapped_column(Float)
    end_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_mileage: Mapped[float] = mapped_column(Float)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    left_censored: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    escalation_count: Mapped[int] = mapped_column(Integer, default=0)
    deescalation_count: Mapped[int] = mapped_column(Integer, default=0)
    class_change_count: Mapped[int] = mapped_column(Integer, default=0)
    stabilized_count: Mapped[int] = mapped_column(Integer, default=0)
    destabilized_count: Mapped[int] = mapped_column(Integer, default=0)
    peak_confidence: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    latest_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    details_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "vehicle_id",
            "hypothesis_class",
            "start_timestamp",
            name="uq_diagnostic_episode_run_vehicle_class_start",
        ),
        Index(
            "ix_diagnostic_episode_run_state_start",
            "run_id",
            "state",
            "start_timestamp",
        ),
        Index(
            "ix_diagnostic_episode_run_vehicle_start",
            "run_id",
            "vehicle_id",
            "start_timestamp",
        ),
        Index(
            "ix_diagnostic_episode_experiment_class",
            "experiment_id",
            "hypothesis_class",
        ),
    )


class DiagnosticCase(Base):
    __tablename__ = "diagnostic_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    episode_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_episodes.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    hypothesis_class: Mapped[str] = mapped_column(String(64), index=True)
    rules_version: Mapped[str] = mapped_column(String(64), index=True)
    source_episode_rules_version: Mapped[str] = mapped_column(String(64), index=True)
    source_event_rules_version: Mapped[str] = mapped_column(String(64), index=True)
    episode_state_at_creation: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    review_priority: Mapped[str] = mapped_column(String(16), index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    start_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    start_mileage: Mapped[float] = mapped_column(Float)
    latest_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latest_mileage: Mapped[float] = mapped_column(Float)
    latest_confidence: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    peak_confidence: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    left_censored: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    note_count: Mapped[int] = mapped_column(Integer, default=0)
    details_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "episode_id",
            name="uq_diagnostic_case_run_episode",
        ),
        Index(
            "ix_diagnostic_case_run_status_priority_updated",
            "run_id",
            "status",
            "review_priority",
            "updated_at",
        ),
        Index(
            "ix_diagnostic_case_run_vehicle_status",
            "run_id",
            "vehicle_id",
            "status",
        ),
        Index(
            "ix_diagnostic_case_experiment_class",
            "experiment_id",
            "hypothesis_class",
        ),
    )


class DiagnosticCaseActivity(Base):
    __tablename__ = "diagnostic_case_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_cases.id", ondelete="CASCADE"),
        index=True,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    activity_type: Mapped[str] = mapped_column(String(48), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="operator")
    from_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        Index(
            "ix_diagnostic_case_activity_case_created",
            "case_id",
            "created_at",
        ),
        Index(
            "ix_diagnostic_case_activity_run_created",
            "run_id",
            "created_at",
        ),
    )


class DiagnosticWatchlistEntry(Base):
    __tablename__ = "diagnostic_watchlist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_cases.id", ondelete="CASCADE"),
        index=True,
    )
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="operator")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "case_id",
            name="uq_diagnostic_watchlist_run_case",
        ),
        Index(
            "ix_diagnostic_watchlist_run_created",
            "run_id",
            "created_at",
        ),
    )


class DiagnosticInvestigationView(Base):
    __tablename__ = "diagnostic_investigation_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="operator")
    name: Mapped[str] = mapped_column(String(96))
    filters_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "name",
            name="uq_diagnostic_investigation_view_run_name",
        ),
        Index(
            "ix_diagnostic_investigation_view_run_updated",
            "run_id",
            "updated_at",
        ),
    )
