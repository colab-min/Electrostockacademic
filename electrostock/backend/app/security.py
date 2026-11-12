import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User

password_hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)
TRACKING_CODE_PATTERN = re.compile(r"^(?:[A-Z0-9]{10}|[A-Z0-9_-]{12})$")
TEMPORARY_PASSWORD_ALLOWED_PATHS = {
    "/api/v1/auth/me",
    "/api/v1/auth/change-password",
}


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def hash_tracking_code(code: str) -> str:
    return hashlib.sha256(code.upper().encode("ascii")).hexdigest()


def normalize_tracking_code(code: str) -> str | None:
    normalized = code.upper()
    if not TRACKING_CODE_PATTERN.fullmatch(normalized):
        return None
    return normalized


def issue_token(user: User, token_type: str = "access", hours: int | None = None) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + (
        timedelta(hours=hours) if hours is not None
        else timedelta(minutes=settings.jwt_access_minutes)
    )
    return jwt.encode(
        {"sub": user.id, "role": user.role, "type": token_type, "exp": expires},
        settings.jwt_secret,
        algorithm="HS256",
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="La sesión no es válida o ha expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload: dict[str, Any] = jwt.decode(
            credentials.credentials,
            get_settings().jwt_secret,
            algorithms=["HS256"],
        )
        if payload.get("type") != "access":
            raise unauthorized
        user = db.get(User, payload.get("sub"))
    except (jwt.PyJWTError, ValueError):
        raise unauthorized from None
    if user is None or not user.active:
        raise unauthorized
    return user


def require_roles(*roles: str):
    def dependency(
        request: Request,
        user: User = Depends(get_current_user),
    ) -> User:
        if (
            user.must_change_password
            and request.url.path not in TEMPORARY_PASSWORD_ALLOWED_PATHS
        ):
            raise HTTPException(
                status_code=403,
                detail="Debe cambiar la contraseña temporal antes de continuar",
            )
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="No tiene permisos para esta sección")
        return user

    return dependency
