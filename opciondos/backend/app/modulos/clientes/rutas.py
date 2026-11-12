"""Rutas del módulo clientes: registro (HU-22), expediente (HU-06) e historial (HU-30)."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.modulos.clientes import servicios
from app.modulos.clientes.esquemas import ContactIn, CustomerIn, NoteIn, VehicleIn
from app.seguridad import CurrentUser, require_roles

router = APIRouter(tags=["clientes"])
FRONT_DESK = ("RECEPTIONIST", "ADMIN")
STAFF = ("RECEPTIONIST", "ADMIN", "MECHANIC")


@router.get("/clientes/vehiculos")
def search_vehicles(q: str = Query(min_length=1, max_length=40), _: CurrentUser = Depends(require_roles(*STAFF)),
                    db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return servicios.search_vehicles(db, q)


@router.get("/clientes/vehiculos/{serie}/expediente")
def technical_record(serie: str, _: CurrentUser = Depends(require_roles(*STAFF)),
                     db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.technical_record(db, serie)


@router.post("/clientes/vehiculos/{vehicle_id}/notas", status_code=201)
def add_note(vehicle_id: int, body: NoteIn, user: CurrentUser = Depends(require_roles("MECHANIC")),
             db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.add_note(db, vehicle_id, body.content_html, user.id)


@router.post("/clientes/vehiculos", status_code=201)
def create_vehicle(body: VehicleIn, user: CurrentUser = Depends(require_roles("CUSTOMER", *FRONT_DESK)),
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.create_vehicle(db, body.model_dump(), user.id, user.role)


@router.get("/clientes/mis-vehiculos")
def my_vehicles(user: CurrentUser = Depends(require_roles("CUSTOMER")),
                db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return servicios.my_vehicles(db, user.id)


@router.get("/clientes/mis-vehiculos/{vehicle_id}/historial")
def history(vehicle_id: int, pagina: int = Query(default=1, ge=1),
            user: CurrentUser = Depends(require_roles("CUSTOMER")), db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.history(db, user.id, vehicle_id, pagina)


@router.get("/clientes")
def find_customer(document_type: Literal["CC", "CE", "PA"], document_number: str = Query(min_length=1, max_length=12),
                  _: CurrentUser = Depends(require_roles(*FRONT_DESK)), db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.find_customer(db, document_type, document_number)


@router.post("/clientes", status_code=201)
def create_customer(body: CustomerIn, user: CurrentUser = Depends(require_roles(*FRONT_DESK)),
                    db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.create_customer(db, body.model_dump(), user.id)


@router.patch("/clientes/{customer_id}")
def update_contact(customer_id: int, body: ContactIn, user: CurrentUser = Depends(require_roles(*FRONT_DESK)),
                   db: Session = Depends(get_db)) -> dict[str, Any]:
    return servicios.update_contact(db, customer_id, body.model_dump(), user.id)
