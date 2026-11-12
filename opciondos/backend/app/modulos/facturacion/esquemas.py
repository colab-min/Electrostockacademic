from typing import Literal

from pydantic import BaseModel, Field


class PagoIn(BaseModel):
    amount: int = Field(ge=0)
    method: Literal["CASH", "CARD", "TRANSFER"] = "CASH"


class EncuestaIn(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)
