from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
