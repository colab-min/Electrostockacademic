from datetime import date

from pydantic import BaseModel, Field

HORA = r"^([01]\d|2[0-3]):00$"


class CitaIn(BaseModel):
    vehicle_id: int
    service_id: int
    fecha: date
    hora: str = Field(pattern=HORA)
    motivo_voltaje: str | None = Field(default=None, max_length=200)


class ReprogramarIn(BaseModel):
    fecha: date
    hora: str = Field(pattern=HORA)


class BloqueoIn(BaseModel):
    bloquear: bool
    motivo: str | None = Field(default=None, max_length=200)
