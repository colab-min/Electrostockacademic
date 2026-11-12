from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

WORK_ORDER_STATUSES = ("RECEIVED", "ASSIGNED", "DIAGNOSING", "WAITING_PARTS", "REPAIRING", "FINISHED",
                       "PENDING_PAYMENT", "PAID", "DELIVERED", "CANCELLED", "PENDING_INSTALLATION")


class WorkOrder(Base):
    __tablename__ = "work_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(12), unique=True)
    tracking_code_hash: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256 del código (RN-25)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), unique=True, nullable=True)
    origin: Mapped[str] = mapped_column(Enum("APPOINTMENT", "WALK_IN", name="work_order_origin"))
    fault_type_id: Mapped[int | None] = mapped_column(ForeignKey("fault_types.id"), nullable=True)
    priority: Mapped[str | None] = mapped_column(Enum("HIGH", "MEDIUM", "LOW", name="wo_priority"), nullable=True)
    mechanic_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(Enum(*WORK_ORDER_STATUSES, name="work_order_status"))
    intake_reason: Mapped[str] = mapped_column(String(500))
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    queue_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WorkOrderStatusHistory(Base):
    __tablename__ = "work_order_status_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"))
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class WorkOrderService(Base):
    __tablename__ = "work_order_services"
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), primary_key=True)
    applied_price: Mapped[int] = mapped_column(Integer)  # precio congelado (RN-31)


class WorkOrderSlot(Base):
    __tablename__ = "work_order_slots"
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), primary_key=True)


class WorkOrderPart(Base):
    __tablename__ = "work_order_parts"
    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"))
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"))
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("part_reservations.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Enum("RESERVED", "INSTALLED", "RETURNED", name="wo_part_status"))


class Sequence(Base):
    __tablename__ = "sequences"
    name: Mapped[str] = mapped_column(String(10), primary_key=True)
    value: Mapped[int] = mapped_column(Integer)
