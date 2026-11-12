"""Rutas del módulo facturacion: /api/facturacion y /api/encuestas."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.modulos.facturacion import servicios
from app.modulos.facturacion.esquemas import EncuestaIn, PagoIn
from app.seguridad import CurrentUser, require_roles

router = APIRouter(tags=["facturacion"])
RECEPCION = require_roles("RECEPTIONIST", "ADMIN")


@router.get("/facturacion/ordenes")
def listar(estado: str | None = None, _: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> list[dict]:
    return servicios.listar(db, estado)


@router.post("/facturacion/ordenes/{order_id}/liquidar")
def liquidar(order_id: int, user: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> dict:
    return servicios.liquidar(db, order_id, user)


@router.post("/facturacion/ordenes/{order_id}/pagos")
def pagar(order_id: int, body: PagoIn, user: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> dict:
    return servicios.pagar(db, order_id, body.amount, body.method, user)


@router.post("/facturacion/ordenes/{order_id}/entregar")
def entregar(order_id: int, user: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> dict:
    return servicios.entregar(db, order_id, user)


@router.get("/facturacion/ordenes/{order_id}/ticket")
def ticket(order_id: int, codigo: str | None = None, user: CurrentUser = Depends(RECEPCION),
           db: Session = Depends(get_db)) -> dict:
    return servicios.ticket(db, order_id, codigo, user)


@router.get("/encuestas/{token}")
def ver_encuesta(token: str, db: Session = Depends(get_db)) -> dict:
    return servicios.ver_encuesta(db, token)


@router.post("/encuestas/{token}")
def responder_encuesta(token: str, body: EncuestaIn, db: Session = Depends(get_db)) -> dict:
    return servicios.responder_encuesta(db, token, body.score, body.comment)
