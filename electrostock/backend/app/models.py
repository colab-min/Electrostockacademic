from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    failed_login_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    login_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True, default=new_id)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("document_type", "document_number", name="uq_customer_document"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    document_type: Mapped[str] = mapped_column(String(10))
    document_number: Mapped[str] = mapped_column(String(20))
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str | None] = mapped_column(String(160))
    data_consent_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("serial_number", name="uq_vehicle_serial"),
        UniqueConstraint("plate", name="uq_vehicle_plate"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    serial_number: Mapped[str] = mapped_column(String(30))
    plate: Mapped[str | None] = mapped_column(String(7))
    brand: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(80))
    year: Mapped[int | None] = mapped_column(Integer)
    battery_capacity_ah: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    cell_type: Mapped[str | None] = mapped_column(String(40))
    motor_power_w: Mapped[int | None] = mapped_column(Integer)
    controller: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Part(Base):
    __tablename__ = "parts"
    __table_args__ = (
        CheckConstraint("physical_stock >= 0", name="ck_part_physical_nonnegative"),
        CheckConstraint("reserved_stock >= 0", name="ck_part_reserved_nonnegative"),
        CheckConstraint("reserved_stock <= physical_stock", name="ck_part_reservation_within_stock"),
        CheckConstraint("unit_price >= 0", name="ck_part_price_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), default="General")
    voltage: Mapped[str | None] = mapped_column(String(20))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    physical_stock: Mapped[int] = mapped_column(Integer, default=0)
    reserved_stock: Mapped[int] = mapped_column(Integer, default=0)
    min_threshold: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ServicePart(Base):
    __tablename__ = "service_parts"
    __table_args__ = (UniqueConstraint("service_id", "part_id", name="uq_service_part"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"))
    part_id: Mapped[str] = mapped_column(ForeignKey("parts.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        UniqueConstraint("slot_date", "start_time", name="uq_slot_datetime"),
        CheckConstraint("booked_count <= capacity", name="ck_slot_capacity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slot_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[str] = mapped_column(String(5))
    capacity: Mapped[int] = mapped_column(Integer, default=3)
    booked_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_reason: Mapped[str | None] = mapped_column(String(200))


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"))
    slot_id: Mapped[str] = mapped_column(ForeignKey("slots.id"))
    status: Mapped[str] = mapped_column(String(20), default="CONFIRMED", index=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(200))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AppointmentSlot(Base):
    __tablename__ = "appointment_slots"

    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    slot_id: Mapped[str] = mapped_column(
        ForeignKey("slots.id"),
        primary_key=True,
        index=True,
    )


class AppointmentPartReservation(Base):
    __tablename__ = "appointment_part_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_appointment_part_quantity_positive"),
    )

    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    part_id: Mapped[str] = mapped_column(
        ForeignKey("parts.id"),
        primary_key=True,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer)


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    tracking_code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    appointment_id: Mapped[str | None] = mapped_column(ForeignKey("appointments.id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    mechanic_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED", index=True)
    fault_description: Mapped[str] = mapped_column(Text, default="")
    fault_type: Mapped[str] = mapped_column(String(10), default="F03")
    fault_priority: Mapped[str] = mapped_column(String(10), default="MEDIUM")
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    diagnosis: Mapped[str] = mapped_column(Text, default="")
    expected_part_date: Mapped[date | None] = mapped_column(Date)
    expected_part_id: Mapped[str | None] = mapped_column(ForeignKey("parts.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    queue_position: Mapped[int | None] = mapped_column(Integer)
    scheduled_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    scope: Mapped[str] = mapped_column(String(30), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SequenceCounter(Base):
    __tablename__ = "sequence_counters"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer)


class WorkOrderSlot(Base):
    __tablename__ = "work_order_slots"

    work_order_id: Mapped[str] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        primary_key=True,
    )
    slot_id: Mapped[str] = mapped_column(
        ForeignKey("slots.id"),
        primary_key=True,
        index=True,
    )


class WorkOrderService(Base):
    __tablename__ = "work_order_services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"))
    service_name: Mapped[str] = mapped_column(String(120))
    applied_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class WorkOrderPart(Base):
    __tablename__ = "work_order_parts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"))
    part_id: Mapped[str] = mapped_column(ForeignKey("parts.id"))
    part_name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="RESERVED")
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TechnicalNote(Base):
    __tablename__ = "technical_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    part_id: Mapped[str] = mapped_column(ForeignKey("parts.id"), index=True)
    movement_type: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(20))
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    receipt_number: Mapped[str] = mapped_column(String(20), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), unique=True)
    token: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    score: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(String(500))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40), index=True)
    entity: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    appointment_id: Mapped[str | None] = mapped_column(ForeignKey("appointments.id"))
    work_order_id: Mapped[str | None] = mapped_column(ForeignKey("work_orders.id"))
    kind: Mapped[str] = mapped_column(String(30))
    recipient: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
