"""Seguridad mínima: Argon2id, JWT corto, autorización por rol y límite de intentos de login."""

import hashlib
import secrets
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import config
from app.db import get_db

_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)  # parámetros OWASP
NO_PERMISSION = "No tiene permisos para esta sección"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def issue_access_token(user_id: int, role: str, must_change_password: bool) -> str:
    now = datetime.now(config.TZ)
    claims = {"sub": str(user_id), "rol": role, "mcp": must_change_password, "jti": str(uuid.uuid4()),
              "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=config.ACCESS_MINUTES)).timestamp())}
    return jwt.encode(claims, config.JWT_SECRET, algorithm="HS256")


@dataclass(frozen=True)
class CurrentUser:
    id: int
    role: str
    must_change_password: bool


def current_user(request: Request) -> CurrentUser:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Se requiere iniciar sesión.")
    try:
        claims = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"], options={"require": ["sub", "rol", "exp"]})
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "La sesión no es válida o expiró.") from exc
    return CurrentUser(int(claims["sub"]), claims["rol"], bool(claims.get("mcp")))


def require_roles(*roles: str, allow_pending_password: bool = False) -> Callable[..., CurrentUser]:
    """Dependencia de cada ruta protegida: niega por defecto y audita el intento rechazado (HU-10)."""

    def dependency(request: Request, user: CurrentUser = Depends(current_user),
                   db: Session = Depends(get_db)) -> CurrentUser:
        if user.must_change_password and not allow_pending_password:
            raise HTTPException(403, "Debe cambiar la contraseña temporal antes de continuar.")
        if user.role not in roles:
            from app.modulos.auditoria.servicios import registrar

            registrar(db, "access", "ACCESS_DENIED", user.id,
                      detail={"role": user.role, "resource": f"{request.method} {request.url.path}"})
            db.commit()
            raise HTTPException(403, NO_PERMISSION)
        return user

    return dependency


class LoginLimiter:
    """5 intentos fallidos en 15 minutos por IP y correo (RNF-13). En memoria: suficiente para la demo."""

    def __init__(self, limit: int = 5, window_s: int = 15 * 60) -> None:
        self.limit, self.window = limit, window_s
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str) -> deque[float]:
        q, cutoff = self.failures[key], time.time() - self.window
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.limit

    def fail(self, key: str) -> None:
        self._recent(key).append(time.time())

    def reset(self, key: str) -> None:
        self.failures.pop(key, None)


login_limiter = LoginLimiter()
