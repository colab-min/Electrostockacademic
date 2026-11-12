from datetime import date, datetime, time

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, String, Time,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

APPOINTMENT_STATUSES = ("HELD", "CONFIRMED", "RESCHEDULED", "CANCELLED", "NO_SHOW", "ATTENDED", "EXPIRED")


class Slot(Base):
    """Franja de 1 hora, en hora local del taller."""

    __tablename__ = "slots"
    __table_args__ = (UniqueConstraint("slot_date", "start_time"), CheckConstraint("booked_count <= capacity"))
    id: Mapped[int] = mapped_column(primary_key=True)
    slot_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    capacity: Mapped[int] = mapped_column(Integer)
    booked_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    block_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    status: Mapped[str] = mapped_column(Enum(*APPOINTMENT_STATUSES, name="appointment_status"))
    starts_at: Mapped[datetime] = mapped_column(DateTime)  # hora local del taller
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AppointmentSlot(Base):
    __tablename__ = "appointment_slots"
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), primary_key=True)


class Notification(Base):
    """Outbox de recordatorios (HU-12); el envío es simulado."""

    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"))
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(Enum("PENDING", "SENT", "UNDELIVERED", name="notification_status"))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
