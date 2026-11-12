"""Rutas del módulo catalogo (HU-18, HU-26)."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.modulos.catalogo import servicios
from app.modulos.catalogo.esquemas import ServiceIn, ServicePartIn, ServiceUpdate
from app.seguridad import CurrentUser, require_roles

router = APIRouter(tags=["catalogo"])
TODOS = ("CUSTOMER", "RECEPTIONIST", "MECHANIC", "ADMIN")


@router.get("/catalogo/servicios")
def listar(todos: bool = False, user: CurrentUser = Depends(require_roles(*TODOS)),
           db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return servicios.listar_servicios(db, todos and user.role == "ADMIN")


@router.post("/catalogo/servicios", status_code=201)
def crear(body: ServiceIn, user: CurrentUser = Depends(require_roles("ADMIN")),
          db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.crear_servicio(db, body.model_dump(), user.id)


@router.patch("/catalogo/servicios/{service_id}")
def editar(service_id: int, body: ServiceUpdate, user: CurrentUser = Depends(require_roles("ADMIN")),
           db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.editar_servicio(db, service_id, body.model_dump(), user.id)


@router.put("/catalogo/servicios/{service_id}/repuestos")
def repuestos(service_id: int, body: list[ServicePartIn], user: CurrentUser = Depends(require_roles("ADMIN")),
              db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.definir_repuestos(db, service_id, [l.model_dump() for l in body], user.id)


@router.get("/catalogo/fallas")
def fallas(_: CurrentUser = Depends(require_roles("RECEPTIONIST", "ADMIN")),
           db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return servicios.listar_fallas(db)
