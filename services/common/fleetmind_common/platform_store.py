"""Persistence models for FleetMind Phases 8.2 through 9.5."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# Register existing diagnostic tables in Base.metadata before resolving FKs.
from . import diagnostic_store as _diagnostic_store  # noqa: F401


class DiagnosticRecommendationOutcome(Base):
    __tablename__ = "diagnostic_recommendation_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_operational_recommendations.id", ondelete="CASCADE"),
        index=True,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    recommendation_type: Mapped[str] = mapped_column(String(64), index=True)

    evaluation_key: Mapped[str] = mapped_column(String(64), index=True)
    evaluation_version: Mapped[str] = mapped_column(String(64), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    observation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observation_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    baseline_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    post_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    factors_json: Mapped[str] = mapped_column(Text, default="[]")
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    materialized_by: Mapped[str] = mapped_column(String(64), default="operator")

    __table_args__ = (
        UniqueConstraint(
            "evaluation_key",
            name="uq_diagnostic_recommendation_outcome_evaluation_key",
        ),
        Index(
            "ix_diag_recommendation_outcome_run_status",
            "run_id",
            "status",
        ),
        Index(
            "ix_diag_recommendation_outcome_vehicle_updated",
            "vehicle_id",
            "updated_at",
        ),
    )


class DiagnosticRecommendationPolicy(Base):
    __tablename__ = "diagnostic_recommendation_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_key: Mapped[str] = mapped_column(String(96), index=True)
    version: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    rules_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="operator")
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    promoted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rollback_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint(
            "policy_key",
            "version",
            name="uq_diagnostic_recommendation_policy_key_version",
        ),
        Index(
            "ix_diag_recommendation_policy_status_updated",
            "status",
            "updated_at",
        ),
    )


class DiagnosticPolicyEvaluation(Base):
    __tablename__ = "diagnostic_policy_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_recommendation_policies.id", ondelete="CASCADE"),
        index=True,
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    evaluation_key: Mapped[str] = mapped_column(String(64), index=True)
    rules_version: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="operator")
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    input_source: Mapped[str] = mapped_column(String(48), index=True)
    input_is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_suppressed: Mapped[int] = mapped_column(Integer, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    candidates_json: Mapped[str] = mapped_column(Text, default="[]")

    __table_args__ = (
        UniqueConstraint(
            "evaluation_key",
            name="uq_diagnostic_policy_evaluation_key",
        ),
        Index(
            "ix_diag_policy_evaluation_policy_created",
            "policy_id",
            "created_at",
        ),
    )


class DiagnosticShadowExperiment(Base):
    __tablename__ = "diagnostic_shadow_experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_key: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_model_runs.id", ondelete="CASCADE"),
        index=True,
    )
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    control_policy_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_recommendation_policies.id", ondelete="CASCADE"),
        index=True,
    )
    candidate_policy_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_recommendation_policies.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="COMPLETED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="operator")
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    input_source: Mapped[str] = mapped_column(String(48), index=True)
    input_is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    frozen_input_json: Mapped[str] = mapped_column(Text, default="[]")
    control_result_json: Mapped[str] = mapped_column(Text, default="{}")
    candidate_result_json: Mapped[str] = mapped_column(Text, default="{}")
    comparison_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        UniqueConstraint(
            "experiment_key",
            name="uq_diagnostic_shadow_experiment_key",
        ),
        Index(
            "ix_diag_shadow_experiment_run_created",
            "run_id",
            "created_at",
        ),
    )


class DiagnosticModelRegistryEntry(Base):
    __tablename__ = "diagnostic_model_registry_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    lineage: Mapped[str] = mapped_column(String(96), index=True)
    source_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(32), default="CANDIDATE", index=True)
    artifact_uri: Mapped[str] = mapped_column(Text)
    artifact_sha256: Mapped[str] = mapped_column(String(64), index=True)
    feature_schema_sha256: Mapped[str] = mapped_column(String(64), index=True)
    benchmark_snapshot_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    benchmark_status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    feature_baseline_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="operator")
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    promoted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_sync_json: Mapped[str] = mapped_column(Text, default="{}")
    notes: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint(
            "model_name",
            "version",
            name="uq_diagnostic_model_registry_name_version",
        ),
        Index(
            "ix_diag_model_registry_stage_created",
            "stage",
            "created_at",
        ),
    )


class AssetTelemetryRecord(Base):
    __tablename__ = "asset_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    experiment_id: Mapped[str] = mapped_column(String(64), index=True)
    asset_id: Mapped[str] = mapped_column(String(64), index=True)
    asset_type: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    site: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    firmware: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    attention_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    status: Mapped[str] = mapped_column(String(16), default="healthy", index=True)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_asset_telemetry_event_id"),
        Index(
            "ix_asset_telemetry_asset_timestamp",
            "asset_id",
            "timestamp",
        ),
        Index(
            "ix_asset_telemetry_type_status_timestamp",
            "asset_type",
            "status",
            "timestamp",
        ),
    )
