from typing import Literal

from pydantic import BaseModel, Field

from app.modulos.inventario.modelos import CATEGORIES

Categoria = Literal[CATEGORIES]  # type: ignore[valid-type]


class PartIn(BaseModel):
    sku: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=120)
    category: Categoria
    purchase_price: int
    sale_price: int
    physical_stock: int = 0
    min_threshold: int = Field(default=0, ge=0)
    compatible_voltage_v: int | None = Field(default=None, gt=0)


class PartUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: Categoria | None = None
    purchase_price: int | None = None
    sale_price: int | None = None
    min_threshold: int | None = Field(default=None, ge=0)
    compatible_voltage_v: int | None = Field(default=None, gt=0)
    active: bool | None = None


class MovementIn(BaseModel):
    part_id: int
    type: Literal["IN", "WRITE_OFF", "ADJUSTMENT"]
    quantity: int  # IN y WRITE_OFF: > 0; ADJUSTMENT: diferencia con signo frente al conteo físico
    reason: str | None = Field(default=None, max_length=200)
