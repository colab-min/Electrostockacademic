from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

CATEGORIES = ("BATTERY", "CONTROLLER", "MOTOR", "CHARGER", "BRAKES", "WHEELS", "CONTROLS", "OTHER")


class Part(Base):
    """Repuesto con tres cantidades: físico, reservado y disponible = físico - reservado (RN-15)."""

    __tablename__ = "parts"
    __table_args__ = (
        CheckConstraint("physical_stock >= 0 AND reserved_stock >= 0 AND reserved_stock <= physical_stock"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(Enum(*CATEGORIES, name="part_category"))
    purchase_price: Mapped[int] = mapped_column(Integer)
    sale_price: Mapped[int] = mapped_column(Integer)
    physical_stock: Mapped[int] = mapped_column(Integer)
    reserved_stock: Mapped[int] = mapped_column(Integer, default=0)
    min_threshold: Mapped[int] = mapped_column(Integer, default=0)
    compatible_voltage_v: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def available(self) -> int:
        return self.physical_stock - self.reserved_stock


class PartReservation(Base):
    __tablename__ = "part_reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"))
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    work_order_id: Mapped[int | None] = mapped_column(ForeignKey("work_orders.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Enum("ACTIVE", "CONSUMED", "RELEASED", "EXPIRED", name="reservation_status"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"))
    type: Mapped[str] = mapped_column(Enum("IN", "WRITE_OFF", "CONSUMPTION", "ADJUSTMENT", name="movement_type"))
    quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
