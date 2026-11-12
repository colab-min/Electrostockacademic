from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (CheckConstraint("total = subtotal + vat"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), unique=True)
    number: Mapped[str] = mapped_column(String(12), unique=True)
    subtotal: Mapped[int] = mapped_column(Integer)
    vat: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), unique=True)
    amount: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(Enum("CASH", "CARD", "TRANSFER", name="payment_method"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Survey(Base):
    __tablename__ = "surveys"
    __table_args__ = (CheckConstraint("score IS NULL OR score BETWEEN 1 AND 5"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), unique=True)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
