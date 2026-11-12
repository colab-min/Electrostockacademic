import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PHONE = r"^\+?[\d\s-]{7,20}$"
VehicleType = Literal["E_BIKE", "SCOOTER", "KICK_SCOOTER", "MOTORCYCLE", "UNICYCLE", "MICROCAR", "QUADRICYCLE"]


def _blank_to_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


class VehicleIn(BaseModel):
    """HU-22: serie 5-30 letras/números/guiones; placa opcional ABC12D (moto) o ABC123."""

    type: VehicleType
    serial_number: str = Field(pattern=r"^[A-Za-z0-9-]{5,30}$")
    plate: str | None = Field(default=None, pattern=r"^([A-Z]{3}\d{2}[A-Z]|[A-Z]{3}\d{3})$")
    brand: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=60)
    year: int = Field(ge=1990, le=2100)
    nominal_voltage_v: int = Field(ge=1, le=1000)
    battery_capacity_ah: Decimal = Field(gt=0, le=99999, decimal_places=1)
    battery_cell: str | None = Field(default=None, max_length=60)
    power_w: int | None = Field(default=None, ge=1, le=100000)
    controller: str | None = Field(default=None, max_length=80)
    customer_id: int | None = None  # solo recepción/admin; el cliente registra el suyo

    @field_validator("battery_cell", "power_w", "controller", mode="before")
    @classmethod
    def blank(cls, value: object) -> object:
        return _blank_to_none(value)

    @field_validator("plate", mode="before")
    @classmethod
    def upper_plate(cls, value: object) -> object:
        value = _blank_to_none(value)
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("serial_number", "brand", "model", mode="before")
    @classmethod
    def strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CustomerIn(BaseModel):
    document_type: Literal["CC", "CE", "PA"]
    document_number: str
    full_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(pattern=PHONE)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL)
    data_consent: bool = False
    vehicle: VehicleIn

    @field_validator("email", mode="before")
    @classmethod
    def blank(cls, value: object) -> object:
        return _blank_to_none(value)

    @field_validator("document_number")
    @classmethod
    def document(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        rule = r"^\d{6,10}$" if info.data.get("document_type") == "CC" else r"^[A-Za-z0-9]{6,12}$"
        if not re.match(rule, value):
            raise ValueError("documento inválido")
        return value


class ContactIn(BaseModel):
    phone: str = Field(pattern=PHONE)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL)

    @field_validator("email", mode="before")
    @classmethod
    def blank(cls, value: object) -> object:
        return _blank_to_none(value)


class NoteIn(BaseModel):
    content_html: str = Field(min_length=1, max_length=20000)
