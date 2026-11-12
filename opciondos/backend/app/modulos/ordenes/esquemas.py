from pydantic import BaseModel, Field


class CrearDesdeCitaIn(BaseModel):
    appointment_id: int
    intake_reason: str | None = Field(default=None, max_length=500)


class IngresoIn(BaseModel):
    vehicle_id: int
    # Opcionales para responder con el texto exacto de la HU ("Seleccione el servicio") y no con el 422 genérico.
    fault_type_id: int | None = None
    service_id: int | None = None
    intake_reason: str | None = Field(default=None, max_length=500)


class CancelarIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)
    version: int | None = None


class EstadoIn(BaseModel):
    to_status: str = Field(max_length=30)
    version: int
    reason: str | None = Field(default=None, max_length=300)


class DiagnosticoIn(BaseModel):
    diagnosis: str = Field(min_length=1, max_length=5000)
    version: int


class AsignacionIn(BaseModel):
    mechanic_id: int
    version: int | None = None


class RepuestoIn(BaseModel):
    part_id: int
    quantity: int = Field(ge=1, le=100)
    voltage_reason: str | None = Field(default=None, max_length=300)


class ServicioIn(BaseModel):
    service_id: int
