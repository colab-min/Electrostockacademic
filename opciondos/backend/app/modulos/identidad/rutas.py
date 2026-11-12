"""/api/auth y /api/usuarios. El token de renovación viaja solo en cookie HttpOnly."""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import config
from app.db import get_db
from app.modulos.identidad import servicios
from app.modulos.identidad.esquemas import (ChangePasswordIn, LoginIn, RegisterIn, SessionOut, UserIn, UserOut,
                                            UserUpdate)
from app.modulos.identidad.modelos import User
from app.seguridad import CurrentUser, login_limiter, require_roles

router = APIRouter(tags=["identidad"])
ALL = ("CUSTOMER", "RECEPTIONIST", "MECHANIC", "ADMIN")
COOKIE, PATH = "refresh_token", "/api/auth"


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, full_name=user.full_name, email=user.email, role=user.role,
                   must_change_password=user.must_change_password, active=user.active)


def _session(response: Response, user: User, access: str, refresh: str) -> SessionOut:
    response.set_cookie(COOKIE, refresh, max_age=config.REFRESH_HOURS * 3600, path=PATH, httponly=True,
                        samesite="strict", secure=config.COOKIE_SECURE)
    return SessionOut(access_token=access, user=_out(user))


@router.post("/auth/login", response_model=SessionOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    key = f"{request.client.host if request.client else '-'}|{body.email.strip().lower()}"
    if login_limiter.blocked(key):
        raise HTTPException(429, "Demasiados intentos. Intenta de nuevo en 15 minutos")
    try:
        user, access, refresh = servicios.login(db, body.email, body.password)
    except HTTPException:
        login_limiter.fail(key)
        raise
    login_limiter.reset(key)
    return _session(response, user, access, refresh)


@router.post("/auth/refresh", response_model=SessionOut)
def refresh(response: Response, refresh_token: str | None = Cookie(default=None),
            db: Session = Depends(get_db)) -> SessionOut:
    return _session(response, *servicios.refresh(db, refresh_token))


@router.post("/auth/logout", status_code=204)
def logout(response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> None:
    servicios.logout(db, refresh_token)
    response.delete_cookie(COOKIE, path=PATH)


@router.post("/auth/register", response_model=SessionOut, status_code=201)
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)) -> SessionOut:
    return _session(response, *servicios.register_customer(db, body.model_dump()))


@router.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser = Depends(require_roles(*ALL)), db: Session = Depends(get_db)) -> UserOut:
    found = db.get(User, user.id)
    if found is None:
        raise HTTPException(401, "La sesión no es válida o expiró.")
    return _out(found)


@router.post("/auth/change-password", response_model=SessionOut)
def change_password(body: ChangePasswordIn, user: CurrentUser = Depends(require_roles(*ALL, allow_pending_password=True)),
                    db: Session = Depends(get_db)) -> SessionOut:
    found, access = servicios.change_password(db, user.id, body.new_password, body.confirmation)
    return SessionOut(access_token=access, user=_out(found))


@router.get("/usuarios", response_model=list[UserOut])
def list_users(_: CurrentUser = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> list[UserOut]:
    return [_out(u) for u in servicios.list_users(db)]


@router.get("/usuarios/mecanicos")
def mechanics(_: CurrentUser = Depends(require_roles("ADMIN", "RECEPTIONIST")), db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": u.id, "full_name": u.full_name, "active": u.active}
            for u in servicios.list_users(db) if u.role == "MECHANIC"]


@router.post("/usuarios", response_model=UserOut, status_code=201)
def create_user(body: UserIn, admin: CurrentUser = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> UserOut:
    return _out(servicios.create_user(db, body.model_dump(), admin.id))


@router.patch("/usuarios/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, admin: CurrentUser = Depends(require_roles("ADMIN")),
                db: Session = Depends(get_db)) -> UserOut:
    return _out(servicios.update_user(db, user_id, body.model_dump(), admin.id))
