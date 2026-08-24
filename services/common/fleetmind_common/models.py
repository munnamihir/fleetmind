from datetime import datetime
from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
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
    vehicle_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    model: Mapped[str] = mapped_column(String(32))
    factory: Mapped[str] = mapped_column(String(32), index=True)
    firmware: Mapped[str] = mapped_column(String(32), index=True)
    component: Mapped[str] = mapped_column(String(64), index=True)
    failure_mode: Mapped[str] = mapped_column(String(128), index=True)
    pump_revision: Mapped[str] = mapped_column(String(32), index=True)
    failure_mileage: Mapped[float] = mapped_column(Float, index=True)
    fault_code: Mapped[str] = mapped_column(String(32))
    simulation_time_acceleration: Mapped[float] = mapped_column(Float, default=600.0)
