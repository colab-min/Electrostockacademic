"""Rutas del módulo inventario (HU-08, HU-27, HU-29)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.modulos.inventario import servicios
from app.modulos.inventario.esquemas import MovementIn, PartIn, PartUpdate
from app.seguridad import CurrentUser, require_roles

router = APIRouter(tags=["inventario"])


@router.get("/inventario/repuestos")
def repuestos(_: CurrentUser = Depends(require_roles("ADMIN", "MECHANIC")), db: Session = Depends(get_db)) -> list[dict]:
    return servicios.listar_repuestos(db)


@router.post("/inventario/repuestos", status_code=201)
def crear(body: PartIn, user: CurrentUser = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> dict:
    return servicios.crear_repuesto(db, body.model_dump(), user.id)


@router.patch("/inventario/repuestos/{part_id}")
def editar(part_id: int, body: PartUpdate, user: CurrentUser = Depends(require_roles("ADMIN")),
           db: Session = Depends(get_db)) -> dict:
    return servicios.editar_repuesto(db, part_id, body.model_dump(), user.id)


@router.post("/inventario/movimientos", status_code=201)
def movimiento(body: MovementIn, user: CurrentUser = Depends(require_roles("ADMIN")),
               db: Session = Depends(get_db)) -> dict:
    return servicios.registrar_movimiento(db, body.model_dump(), user.id)


@router.get("/inventario/movimientos")
def movimientos(_: CurrentUser = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)) -> list[dict]:
    return servicios.listar_movimientos(db)
