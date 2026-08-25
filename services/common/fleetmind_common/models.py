from datetime import datetime
from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(32))
    factory: Mapped[str] = mapped_column(String(32), index=True)
    firmware: Mapped[str] = mapped_column(String(32), index=True)
    pump_revision: Mapped[str] = mapped_column(String(32), index=True)
    mileage: Mapped[float] = mapped_column(Float)
    ambient_temp_c: Mapped[float] = mapped_column(Float)
    speed_mph: Mapped[float] = mapped_column(Float)
    soc_pct: Mapped[float] = mapped_column(Float)
    pack_voltage_v: Mapped[float] = mapped_column(Float)
    pack_current_a: Mapped[float] = mapped_column(Float)
    battery_temp_c: Mapped[float] = mapped_column(Float)
    cell_imbalance_v: Mapped[float] = mapped_column(Float)
    motor_temp_c: Mapped[float] = mapped_column(Float)
    inverter_temp_c: Mapped[float] = mapped_column(Float)
    motor_rpm: Mapped[float] = mapped_column(Float)
    coolant_temp_c: Mapped[float] = mapped_column(Float)
    pump_rpm: Mapped[float] = mapped_column(Float)
    pump_current_a: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)

    __table_args__ = (
        Index("ix_telemetry_vehicle_timestamp", "vehicle_id", "timestamp"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    risk_score: Mapped[float] = mapped_column(Float)
    title: Mapped[str] = mapped_column(String(128))
    evidence: Mapped[str] = mapped_column(Text)
    firmware: Mapped[str] = mapped_column(String(32), index=True)
    pump_revision: Mapped[str] = mapped_column(String(32), index=True)
    factory: Mapped[str] = mapped_column(String(32), index=True)


class FailureEvent(Base):
    __tablename__ = "failure_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(32))
    factory: Mapped[str] = mapped_column(String(32), index=True)
    firmware: Mapped[str] = mapped_column(String(32), index=True)
    component: Mapped[str] = mapped_column(String(64), index=True)
    failure_mode: Mapped[str] = mapped_column(String(128), index=True)
    pump_revision: Mapped[str] = mapped_column(String(32), index=True)
    failure_mileage: Mapped[float] = mapped_column(Float, index=True)
    fault_code: Mapped[str] = mapped_column(String(32))
    simulation_time_acceleration: Mapped[float] = mapped_column(Float, default=600.0)
    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "vehicle_id",
            name="uq_failure_events_experiment_vehicle",
        ),
    )



class MLModelRun(Base):
    __tablename__ = "ml_model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    algorithm: Mapped[str] = mapped_column(String(64))
    horizon_miles: Mapped[float] = mapped_column(Float)
    window_size: Mapped[int] = mapped_column(Integer)
    train_examples: Mapped[int] = mapped_column(Integer, default=0)
    validation_examples: Mapped[int] = mapped_column(Integer, default=0)
    test_examples: Mapped[int] = mapped_column(Integer, default=0)
    train_positives: Mapped[int] = mapped_column(Integer, default=0)
    validation_positives: Mapped[int] = mapped_column(Integer, default=0)
    test_positives: Mapped[int] = mapped_column(Integer, default=0)
    decision_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    calibration_json: Mapped[str] = mapped_column(Text, default="[]")
    feature_importance_json: Mapped[str] = mapped_column(Text, default="[]")
    leakage_policy_json: Mapped[str] = mapped_column(Text, default="{}")
    notes: Mapped[str] = mapped_column(Text, default="")


class MLBenchmarkSnapshot(Base):
    __tablename__ = "ml_benchmark_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lineage: Mapped[str] = mapped_column(String(64), index=True)
    seed: Mapped[int] = mapped_column(Integer)
    benchmark_fraction: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="locked", index=True)
    example_count: Mapped[int] = mapped_column(Integer)
    positive_count: Mapped[int] = mapped_column(Integer)
    vehicle_count: Mapped[int] = mapped_column(Integer)
    failure_vehicle_count: Mapped[int] = mapped_column(Integer)
    feature_schema_sha256: Mapped[str] = mapped_column(String(64))
    data_sha256: Mapped[str] = mapped_column(String(64))
    artifact_path: Mapped[str] = mapped_column(Text)
    manifest_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        UniqueConstraint("lineage", "seed", name="uq_ml_benchmark_snapshot_lineage_seed"),
    )


class MLPrediction(Base):
    __tablename__ = "ml_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_run_id: Mapped[int] = mapped_column(Integer, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    vehicle_id: Mapped[str] = mapped_column(String(32), index=True)
    probability: Mapped[float] = mapped_column(Float, index=True)
    predicted_label: Mapped[int] = mapped_column(Integer)
    anchor_mileage: Mapped[float] = mapped_column(Float)
    firmware: Mapped[str] = mapped_column(String(32), index=True)
    pump_revision: Mapped[str] = mapped_column(String(32), index=True)
    factory: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(32))
    feature_summary_json: Mapped[str] = mapped_column(Text, default="{}")

    __table_args__ = (
        Index("ix_ml_prediction_run_probability", "model_run_id", "probability"),
    )
