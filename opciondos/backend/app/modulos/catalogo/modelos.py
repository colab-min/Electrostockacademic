from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

PRIORITIES = ("HIGH", "MEDIUM", "LOW")


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (CheckConstraint("labor_price > 0"), CheckConstraint("duration_min > 0"))
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    labor_price: Mapped[int] = mapped_column(Integer)
    duration_min: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ServicePart(Base):
    __tablename__ = "service_parts"
    __table_args__ = (CheckConstraint("quantity > 0"),)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)


class FaultType(Base):
    __tablename__ = "fault_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    priority: Mapped[str] = mapped_column(Enum(*PRIORITIES, name="priority"))
    estimated_minutes: Mapped[int] = mapped_column(Integer)
