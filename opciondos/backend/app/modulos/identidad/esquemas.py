from typing import Literal

from pydantic import BaseModel, Field

EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    document_type: Literal["CC", "CE", "PA"]
    document_number: str = Field(min_length=6, max_length=12)
    phone: str = Field(min_length=7, max_length=20, pattern=r"^\+?[\d\s-]{7,20}$")
    email: str = Field(max_length=254, pattern=EMAIL)
    password: str = Field(max_length=128)
    data_consent: bool = False


class ChangePasswordIn(BaseModel):
    new_password: str = Field(max_length=128)
    confirmation: str = Field(max_length=128)


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    must_change_password: bool
    active: bool = True


class SessionOut(BaseModel):
    access_token: str
    user: UserOut


class UserIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254, pattern=EMAIL)
    role: Literal["RECEPTIONIST", "MECHANIC", "ADMIN"]
    temporary_password: str = Field(max_length=128)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    role: Literal["RECEPTIONIST", "MECHANIC", "ADMIN"] | None = None
    active: bool | None = None
