"""Rutas del módulo agenda (HU-01, HU-02, HU-11, HU-19)."""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.modulos.agenda import servicios
from app.modulos.agenda.esquemas import BloqueoIn, CitaIn, ReprogramarIn
from app.seguridad import CurrentUser, require_roles

router = APIRouter(tags=["agenda"])
CLIENTE = require_roles("CUSTOMER")
RECEPCION = require_roles("RECEPTIONIST", "ADMIN")


@router.get("/agenda/disponibilidad")
def disponibilidad(service_id: int, mes: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
                   _: CurrentUser = Depends(CLIENTE), db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.disponibilidad(db, service_id, mes)


@router.get("/agenda/franjas")
def franjas(service_id: int, fecha: date, _: CurrentUser = Depends(CLIENTE),
            db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return servicios.franjas(db, service_id, fecha)


@router.post("/agenda/citas", status_code=201)
def crear(body: CitaIn, user: CurrentUser = Depends(CLIENTE), db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.crear_cita(db, user, body.model_dump())


@router.get("/agenda/citas/mias")
def mias(user: CurrentUser = Depends(CLIENTE), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return servicios.mis_citas(db, user)


@router.post("/agenda/citas/{appointment_id}/confirmar")
def confirmar(appointment_id: int, user: CurrentUser = Depends(CLIENTE), db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.confirmar(db, user, appointment_id)


@router.post("/agenda/citas/{appointment_id}/cancelar")
def cancelar(appointment_id: int, user: CurrentUser = Depends(CLIENTE), db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.cancelar(db, user, appointment_id)


@router.post("/agenda/citas/{appointment_id}/reprogramar")
def reprogramar(appointment_id: int, body: ReprogramarIn, user: CurrentUser = Depends(CLIENTE),
                db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.reprogramar(db, user, appointment_id, body.model_dump())


@router.get("/agenda/calendario")
def calendario(fecha: date, _: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.calendario(db, fecha)


@router.post("/agenda/franjas/{slot_id}/bloqueo")
def bloqueo(slot_id: int, body: BloqueoIn, user: CurrentUser = Depends(RECEPCION),
            db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.bloqueo(db, user, slot_id, body.model_dump())
