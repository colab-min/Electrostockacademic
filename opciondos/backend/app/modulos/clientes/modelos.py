from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

VEHICLE_TYPES = ("E_BIKE", "SCOOTER", "KICK_SCOOTER", "MOTORCYCLE", "UNICYCLE", "MICROCAR", "QUADRICYCLE")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("document_type", "document_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True, nullable=True)
    document_type: Mapped[str] = mapped_column(Enum("CC", "CE", "PA", name="document_type"))
    document_number: Mapped[str] = mapped_column(String(12))
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    data_consent_at: Mapped[datetime] = mapped_column(DateTime)
    data_consent_version: Mapped[str] = mapped_column(String(10), default="v1")


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    type: Mapped[str] = mapped_column(Enum(*VEHICLE_TYPES, name="vehicle_type"))
    serial_number: Mapped[str] = mapped_column(String(30), unique=True)
    plate: Mapped[str | None] = mapped_column(String(10), unique=True, nullable=True)
    brand: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(60))
    year: Mapped[int] = mapped_column(SmallInteger)
    nominal_voltage_v: Mapped[int] = mapped_column(SmallInteger)
    battery_capacity_ah: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    battery_cell: Mapped[str | None] = mapped_column(String(60), nullable=True)
    power_w: Mapped[int | None] = mapped_column(nullable=True)
    controller: Mapped[str | None] = mapped_column(String(80), nullable=True)


class TechnicalNote(Base):
    __tablename__ = "technical_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id"), nullable=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    content_html: Mapped[str] = mapped_column(Text)  # sanitizado con nh3 antes de guardar
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
