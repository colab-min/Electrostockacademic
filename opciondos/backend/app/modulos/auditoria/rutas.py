"""Rutas del módulo auditoria (HU-20): solo lectura; la tabla es append-only por trigger."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.modulos.auditoria import servicios
from app.seguridad import CurrentUser, require_roles

router = APIRouter(tags=["auditoria"])


@router.get("/auditoria/bitacora")
def log(entidad: str | None = None, accion: str | None = None, _: CurrentUser = Depends(require_roles("ADMIN")),
        db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return servicios.consultar(db, entidad, accion)


@router.get("/auditoria/opciones")
def options(_: CurrentUser = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> dict[str, list[str]]:
    return servicios.opciones(db)
