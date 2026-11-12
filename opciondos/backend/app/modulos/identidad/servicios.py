"""Identidad: login, renovación, registro de clientes, cambio de contraseña temporal y usuarios (HU-21, HU-15)."""

import re
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.modulos.auditoria.servicios import registrar
from app.modulos.clientes.modelos import Customer
from app.modulos.identidad.modelos import RefreshSession, User
from app.seguridad import hash_password, issue_access_token, new_refresh_token, sha256, verify_password

INVALID_CREDENTIALS = "Credenciales inválidas, por favor intenta de nuevo"
DOCUMENT_REGISTERED = "Este documento ya está registrado. Acércate a recepción para actualizar tu correo"
CONSENT_REQUIRED = "Debes autorizar el tratamiento de tus datos para crear la cuenta"


def password_problems(password: str) -> list[str]:
    """RN-43: mínimo 10 caracteres con mayúscula, minúscula, número y símbolo."""
    rules = [(len(password) >= 10, "Debe tener al menos 10 caracteres."),
             (re.search(r"[A-ZÁÉÍÓÚÑ]", password), "Debe incluir una letra mayúscula."),
             (re.search(r"[a-záéíóúñ]", password), "Debe incluir una letra minúscula."),
             (re.search(r"\d", password), "Debe incluir un número."),
             (re.search(r"[^\w\s]|_", password), "Debe incluir un símbolo.")]
    return [message for ok, message in rules if not ok]


def _now() -> datetime:
    return datetime.now(config.TZ).replace(tzinfo=None)


def start_session(db: Session, user: User) -> tuple[str, str]:
    raw = new_refresh_token()
    db.add(RefreshSession(user_id=user.id, token_hash=sha256(raw),
                          expires_at=_now() + timedelta(hours=config.REFRESH_HOURS)))
    return issue_access_token(user.id, user.role, user.must_change_password), raw


def login(db: Session, email: str, password: str) -> tuple[User, str, str]:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.active or not verify_password(user.password_hash, password):
        raise HTTPException(401, INVALID_CREDENTIALS)
    access, refresh = start_session(db, user)
    db.commit()
    return user, access, refresh


def refresh(db: Session, raw: str | None) -> tuple[User, str, str]:
    """Rota el token de renovación en cada uso; el anterior queda revocado."""
    record = db.scalar(select(RefreshSession).where(RefreshSession.token_hash == sha256(raw or "")).with_for_update())
    if record is None or record.revoked_at is not None or record.expires_at <= _now():
        raise HTTPException(401, "La sesión no es válida o expiró.")
    user = db.get(User, record.user_id)
    if user is None or not user.active:
        raise HTTPException(401, "La sesión no es válida o expiró.")
    record.revoked_at = _now()
    access, new_raw = start_session(db, user)
    db.commit()
    return user, access, new_raw


def logout(db: Session, raw: str | None) -> None:
    record = db.scalar(select(RefreshSession).where(RefreshSession.token_hash == sha256(raw or "")))
    if record and record.revoked_at is None:
        record.revoked_at = _now()
        db.commit()


def register_customer(db: Session, data: dict) -> tuple[User, str, str]:
    if not data["data_consent"]:
        raise HTTPException(422, CONSENT_REQUIRED)
    if problems := password_problems(data["password"]):
        raise HTTPException(422, " ".join(problems))
    email = data["email"].strip().lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Este correo ya tiene una cuenta.")
    customer = db.scalar(select(Customer).where(Customer.document_type == data["document_type"],
                                                Customer.document_number == data["document_number"].strip()))
    # RN-47: un documento registrado por recepción se vincula solo si el correo coincide.
    if customer and (customer.user_id or (customer.email or "").lower() != email):
        raise HTTPException(409, DOCUMENT_REGISTERED)
    user = User(full_name=data["full_name"].strip(), email=email, password_hash=hash_password(data["password"]),
                role="CUSTOMER")
    db.add(user)
    db.flush()
    if customer is None:
        customer = Customer(document_type=data["document_type"], document_number=data["document_number"].strip(),
                            full_name=user.full_name, phone=data["phone"].strip(), email=email)
        db.add(customer)
    customer.user_id, customer.data_consent_at, customer.data_consent_version = user.id, _now(), "v1"
    registrar(db, "users", "CUSTOMER_REGISTERED", user.id, user.id)
    access, refresh_token = start_session(db, user)
    db.commit()
    return user, access, refresh_token


def change_password(db: Session, user_id: int, new_password: str, confirmation: str) -> tuple[User, str]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "La sesión no es válida o expiró.")
    problems = password_problems(new_password)
    if verify_password(user.password_hash, new_password):
        problems.append("La nueva contraseña debe ser diferente de la temporal.")
    if new_password != confirmation:
        problems.append("Las contraseñas no coinciden.")
    if problems:
        raise HTTPException(422, " ".join(problems))
    user.password_hash, user.must_change_password = hash_password(new_password), False
    registrar(db, "users", "PASSWORD_CHANGED", user.id, user.id)
    db.commit()
    return user, issue_access_token(user.id, user.role, False)


# --- HU-15: usuarios internos (sencillo) ------------------------------------------------------------
def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.role, User.full_name)))


def create_user(db: Session, data: dict, admin_id: int) -> User:
    if db.scalar(select(User.id).where(User.email == data["email"].lower())):
        raise HTTPException(409, "Este correo ya tiene una cuenta.")
    if problems := password_problems(data["temporary_password"]):
        raise HTTPException(422, " ".join(problems))
    user = User(full_name=data["full_name"], email=data["email"].lower(), role=data["role"],
                password_hash=hash_password(data["temporary_password"]), must_change_password=True)
    db.add(user)
    db.flush()
    registrar(db, "users", "USER_CREATED", admin_id, user.id, {"role": user.role})
    db.commit()
    return user


def update_user(db: Session, user_id: int, data: dict, admin_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado.")
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    if data.get("active") is False:  # RN-45: desactivar revoca sus sesiones
        for s in db.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id,
                                                         RefreshSession.revoked_at.is_(None))):
            s.revoked_at = _now()
    registrar(db, "users", "USER_UPDATED", admin_id, user.id, {k: v for k, v in data.items() if v is not None})
    db.commit()
    return user
