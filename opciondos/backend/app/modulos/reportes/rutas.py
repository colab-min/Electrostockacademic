"""Rutas del módulo reportes (HU-14)."""

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.modulos.reportes import servicios
from app.seguridad import CurrentUser, require_roles
from app.tiempo import ahora

router = APIRouter(tags=["reportes"])


@router.get("/reportes/resumen")
def summary(desde: date | None = None, hasta: date | None = None, _: CurrentUser = Depends(require_roles("ADMIN")),
            db: Session = Depends(get_db)) -> dict[str, Any]:
    hasta = hasta or ahora().date()
    return servicios.summary(db, desde or hasta - timedelta(days=30), hasta)
