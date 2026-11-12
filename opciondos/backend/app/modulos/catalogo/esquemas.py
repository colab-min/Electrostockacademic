from pydantic import BaseModel, Field


class ServiceIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    labor_price: int = Field(gt=0)
    duration_min: int = Field(gt=0)
    active: bool = True


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    labor_price: int | None = Field(default=None, gt=0)
    duration_min: int | None = Field(default=None, gt=0)
    active: bool | None = None


class ServicePartIn(BaseModel):
    part_id: int
    quantity: int = Field(gt=0)
