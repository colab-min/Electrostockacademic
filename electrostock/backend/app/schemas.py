from datetime import date
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class RegisterRequest(APIModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str = Field(min_length=10, max_length=128)
    document_type: str = Field(min_length=2, max_length=10)
    document_number: str = Field(min_length=6, max_length=20)
    phone: str = Field(min_length=7, max_length=20)
    data_consent: bool

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not (
            any(char.islower() for char in value)
            and any(char.isupper() for char in value)
            and any(char.isdigit() for char in value)
            and any(not char.isalnum() for char in value)
        ):
            raise ValueError("La contraseña debe incluir mayúscula, minúscula, número y símbolo")
        return value


class LoginRequest(APIModel):
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str


class PasswordChangeRequest(APIModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not (
            any(char.islower() for char in value)
            and any(char.isupper() for char in value)
            and any(char.isdigit() for char in value)
            and any(not char.isalnum() for char in value)
        ):
            raise ValueError("La contraseña debe incluir mayúscula, minúscula, número y símbolo")
        return value


class CustomerCreate(APIModel):
    full_name: str = Field(min_length=2, max_length=120)
    document_type: str = Field(min_length=2, max_length=10)
    document_number: str = Field(min_length=6, max_length=20)
    phone: str = Field(min_length=7, max_length=20)
    email: str | None = Field(default=None, pattern=EMAIL_PATTERN)
    data_consent: bool


class CustomerUpdate(APIModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    document_type: str | None = Field(default=None, min_length=2, max_length=10)
    document_number: str | None = Field(default=None, min_length=6, max_length=20)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    email: str | None = Field(default=None, pattern=EMAIL_PATTERN)


class VehicleCreate(APIModel):
    customer_id: str | None = None
    serial_number: str = Field(min_length=5, max_length=30)
    plate: str | None = Field(default=None, max_length=7)
    brand: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=80)
    year: int | None = Field(default=None, ge=1900, le=2100)
    battery_capacity_ah: Decimal | None = Field(default=None, gt=0, max_digits=6, decimal_places=2)
    cell_type: str | None = Field(default=None, max_length=40)
    motor_power_w: int | None = Field(default=None, gt=0)
    controller: str | None = Field(default=None, max_length=60)


class VehicleUpdate(APIModel):
    customer_id: str | None = None
    serial_number: str | None = Field(default=None, min_length=5, max_length=30)
    plate: str | None = Field(default=None, max_length=7)
    brand: str | None = Field(default=None, min_length=1, max_length=60)
    model: str | None = Field(default=None, min_length=1, max_length=80)
    year: int | None = Field(default=None, ge=1900, le=2100)
    battery_capacity_ah: Decimal | None = Field(default=None, gt=0, max_digits=6, decimal_places=2)
    cell_type: str | None = Field(default=None, max_length=40)
    motor_power_w: int | None = Field(default=None, gt=0)
    controller: str | None = Field(default=None, max_length=60)


class ServiceCreate(APIModel):
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    duration_minutes: int = Field(gt=0, le=1440)


class ServiceUpdate(APIModel):
    code: str | None = Field(default=None, min_length=2, max_length=30)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    duration_minutes: int | None = Field(default=None, gt=0, le=1440)
    active: bool | None = None


class PartCreate(APIModel):
    sku: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(default="General", max_length=60)
    voltage: str | None = Field(default=None, max_length=20)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    physical_stock: int = Field(default=0, ge=0)
    min_threshold: int = Field(default=0, ge=0)


class PartUpdate(APIModel):
    sku: str | None = Field(default=None, min_length=2, max_length=40)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, max_length=60)
    voltage: str | None = Field(default=None, max_length=20)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    min_threshold: int | None = Field(default=None, ge=0)
    active: bool | None = None


class UserUpdate(APIModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, pattern=EMAIL_PATTERN)
    role: Literal["RECEPTIONIST", "MECHANIC", "ADMIN"] | None = None
    active: bool | None = None


class InternalUserCreate(APIModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=EMAIL_PATTERN)
    role: Literal["RECEPTIONIST", "MECHANIC", "ADMIN"]
    temporary_password: str = Field(min_length=10, max_length=128)

    @field_validator("temporary_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not (
            any(char.islower() for char in value)
            and any(char.isupper() for char in value)
            and any(char.isdigit() for char in value)
            and any(not char.isalnum() for char in value)
        ):
            raise ValueError("La contraseña debe incluir mayúscula, minúscula, número y símbolo")
        return value


class AppointmentCreate(APIModel):
    vehicle_id: str
    service_id: str
    slot_id: str


class RescheduleRequest(APIModel):
    slot_id: str


class CancelRequest(APIModel):
    reason: str = Field(default="", max_length=200)


class WorkOrderCreate(APIModel):
    appointment_code: str | None = None
    vehicle_id: str | None = None
    customer_id: str | None = None
    service_id: str | None = None
    fault_type: Literal["F01", "F02", "F03", "F04"] | None = None
    fault_description: str = Field(default="", max_length=2000)


class AssignmentRequest(APIModel):
    mechanic_id: str
    version: int = Field(ge=1)


class StatusRequest(APIModel):
    status: str
    reason: str | None = Field(default=None, max_length=500)
    expected_part_id: str | None = None
    expected_part_date: date | None = None


class DiagnosisRequest(APIModel):
    diagnosis: str = Field(min_length=1, max_length=5000)


class AddPartRequest(APIModel):
    part_id: str
    quantity: int = Field(ge=1, le=100)


class AddServiceRequest(APIModel):
    service_id: str


class ServicePartAssignment(APIModel):
    part_id: str
    quantity: int = Field(gt=0, le=100)


class InventoryMovementRequest(APIModel):
    part_id: str
    type: str
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=300)

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"IN", "WRITE_OFF", "ADJUSTMENT"}:
            raise ValueError("El tipo debe ser IN, WRITE_OFF o ADJUSTMENT")
        return normalized


class PaymentRequest(APIModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: str = Field(min_length=2, max_length=20)


class SurveyRequest(APIModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)
