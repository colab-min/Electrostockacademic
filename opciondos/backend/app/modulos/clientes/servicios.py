"""Clientes, vehículos, expediente técnico e historial (HU-22, HU-06, HU-30)."""

from typing import Any

import nh3
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modulos.auditoria.servicios import registrar
from app.modulos.catalogo.modelos import Service
from app.modulos.clientes.modelos import Customer, TechnicalNote, Vehicle
from app.modulos.facturacion.modelos import Payment
from app.modulos.identidad.modelos import User
from app.modulos.inventario.modelos import Part
from app.modulos.ordenes.modelos import WorkOrder, WorkOrderPart, WorkOrderService, WorkOrderStatusHistory
from app.tiempo import ahora

SERIAL_TAKEN = "El número de serie ingresado ya se encuentra registrado"
PLATE_TAKEN = "La placa ingresada ya se encuentra registrada"
CONSENT_REQUIRED = "Debe registrar la autorización del cliente para continuar"
DOCUMENT_TAKEN = "Este documento ya está registrado."
CUSTOMER_NOT_FOUND = "Cliente no encontrado."
VEHICLE_NOT_FOUND = "No se encontró un vehículo con esa serie, placa o documento."
NOTE_TAGS = {"p", "br", "div", "strong", "b", "em", "i", "ul", "ol", "li"}


def sanitize(html: str) -> str:
    """Lista blanca de formato básico; sin atributos, así no sobreviven onerror, style ni href."""
    return nh3.clean(html, tags=NOTE_TAGS, attributes={}).strip()


def vehicle_out(v: Vehicle) -> dict[str, Any]:
    return {"id": v.id, "type": v.type, "serial_number": v.serial_number, "plate": v.plate, "brand": v.brand,
            "model": v.model, "nominal_voltage_v": v.nominal_voltage_v}


def vehicle_full(v: Vehicle) -> dict[str, Any]:
    return {**vehicle_out(v), "year": v.year, "battery_capacity_ah": float(v.battery_capacity_ah),
            "battery_cell": v.battery_cell, "power_w": v.power_w, "controller": v.controller}


def customer_out(db: Session, c: Customer) -> dict[str, Any]:
    vehicles = db.scalars(select(Vehicle).where(Vehicle.customer_id == c.id).order_by(Vehicle.id))
    return {"id": c.id, "document_type": c.document_type, "document_number": c.document_number,
            "full_name": c.full_name, "phone": c.phone, "email": c.email, "has_account": c.user_id is not None,
            "vehicles": [vehicle_out(v) for v in vehicles]}


# --- HU-22 ------------------------------------------------------------------------------------------
def find_customer(db: Session, document_type: str, document_number: str) -> dict[str, Any]:
    c = db.scalar(select(Customer).where(Customer.document_type == document_type,
                                         Customer.document_number == document_number.strip()))
    if c is None:
        raise HTTPException(404, CUSTOMER_NOT_FOUND)
    return customer_out(db, c)


def _check_unique(db: Session, data: dict[str, Any]) -> None:
    if db.scalar(select(Vehicle.id).where(Vehicle.serial_number == data["serial_number"])):
        raise HTTPException(409, SERIAL_TAKEN)
    if data.get("plate") and db.scalar(select(Vehicle.id).where(Vehicle.plate == data["plate"])):
        raise HTTPException(409, PLATE_TAKEN)


def _add_vehicle(db: Session, customer_id: int, data: dict[str, Any], user_id: int) -> Vehicle:
    # shortcut: la unicidad se verifica antes de insertar; dos registros simultáneos de la misma serie
    # terminarían en el índice único (500). Suficiente para la demo.
    _check_unique(db, data)
    fields = {k: v for k, v in data.items() if k != "customer_id"}
    vehicle = Vehicle(customer_id=customer_id, **fields)
    db.add(vehicle)
    db.flush()
    registrar(db, "vehicles", "VEHICLE_CREATED", user_id, vehicle.id,
              {"serial_number": vehicle.serial_number, "customer_id": customer_id})
    return vehicle


def create_customer(db: Session, data: dict[str, Any], user_id: int) -> dict[str, Any]:
    if not data["data_consent"]:
        raise HTTPException(422, CONSENT_REQUIRED)
    if db.scalar(select(Customer.id).where(Customer.document_type == data["document_type"],
                                           Customer.document_number == data["document_number"])):
        raise HTTPException(409, DOCUMENT_TAKEN)
    _check_unique(db, data["vehicle"])
    customer = Customer(document_type=data["document_type"], document_number=data["document_number"],
                        full_name=data["full_name"].strip(), phone=data["phone"].strip(),
                        email=data["email"].lower() if data["email"] else None,
                        data_consent_at=ahora(), data_consent_version="v1")
    db.add(customer)
    db.flush()
    registrar(db, "customers", "CUSTOMER_CREATED", user_id, customer.id, {"consent_version": "v1"})
    vehicle = _add_vehicle(db, customer.id, data["vehicle"], user_id)
    db.commit()
    return {"customer_id": customer.id, "vehicle_id": vehicle.id}


def update_contact(db: Session, customer_id: int, data: dict[str, Any], user_id: int) -> dict[str, Any]:
    c = db.get(Customer, customer_id)
    if c is None:
        raise HTTPException(404, CUSTOMER_NOT_FOUND)
    before = {"phone": c.phone, "email": c.email}
    c.phone, c.email = data["phone"].strip(), data["email"].lower() if data["email"] else None
    registrar(db, "customers", "CONTACT_UPDATED", user_id, c.id,
              {"before": before, "after": {"phone": c.phone, "email": c.email}})
    db.commit()
    return customer_out(db, c)


def create_vehicle(db: Session, data: dict[str, Any], user_id: int, role: str) -> dict[str, Any]:
    if role == "CUSTOMER":
        customer_id = db.scalar(select(Customer.id).where(Customer.user_id == user_id))
    else:
        customer_id = data.get("customer_id") and db.scalar(select(Customer.id).where(Customer.id == data["customer_id"]))
    if not customer_id:
        raise HTTPException(404, CUSTOMER_NOT_FOUND)
    vehicle = _add_vehicle(db, customer_id, data, user_id)
    db.commit()
    return vehicle_out(vehicle)


def my_vehicles(db: Session, user_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(select(Vehicle).join(Customer, Customer.id == Vehicle.customer_id)
                      .where(Customer.user_id == user_id).order_by(Vehicle.id))
    return [vehicle_out(v) for v in rows]


# --- HU-06 ------------------------------------------------------------------------------------------
def search_vehicles(db: Session, q: str) -> list[dict[str, Any]]:
    q = q.strip()
    rows = db.execute(select(Vehicle, Customer).join(Customer, Customer.id == Vehicle.customer_id)
                      .where(or_(Vehicle.serial_number == q, Vehicle.plate == q.upper(),
                                 Customer.document_number == q))
                      .order_by(Vehicle.id).limit(50))
    return [{**vehicle_out(v), "customer": {"id": c.id, "full_name": c.full_name, "document_type": c.document_type,
                                            "document_number": c.document_number}} for v, c in rows]


def _orders(db: Session, vehicle_id: int, delivered_only: bool = False,
            limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
    query = select(WorkOrder).where(WorkOrder.vehicle_id == vehicle_id)
    if delivered_only:
        query = query.where(WorkOrder.status == "DELIVERED")
    orders = list(db.scalars(query.order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())
                             .offset(offset).limit(limit)))
    result = []
    for o in orders:
        services = db.scalars(select(Service.name).join(WorkOrderService, WorkOrderService.service_id == Service.id)
                              .where(WorkOrderService.work_order_id == o.id))
        parts = db.execute(select(Part.sku, Part.name, WorkOrderPart.quantity)
                           .join(WorkOrderPart, WorkOrderPart.part_id == Part.id)
                           .where(WorkOrderPart.work_order_id == o.id, WorkOrderPart.status == "INSTALLED"))
        delivered_at = db.scalar(select(WorkOrderStatusHistory.created_at).where(
            WorkOrderStatusHistory.work_order_id == o.id, WorkOrderStatusHistory.to_status == "DELIVERED"))
        result.append({"id": o.id, "number": o.number, "status": o.status, "created_at": o.created_at,
                       "delivered_at": delivered_at, "intake_reason": o.intake_reason, "diagnosis": o.diagnosis,
                       "services": list(services),
                       "parts": [{"sku": s, "name": n, "quantity": q} for s, n, q in parts],
                       "total_paid": db.scalar(select(Payment.amount).where(Payment.work_order_id == o.id))})
    return result


def technical_record(db: Session, serial: str) -> dict[str, Any]:
    row = db.execute(select(Vehicle, Customer).join(Customer, Customer.id == Vehicle.customer_id)
                     .where(Vehicle.serial_number == serial.strip())).first()
    if row is None:
        raise HTTPException(404, VEHICLE_NOT_FOUND)
    v, c = row
    notes = db.execute(select(TechnicalNote, User.full_name).join(User, User.id == TechnicalNote.author_id)
                       .where(TechnicalNote.vehicle_id == v.id)
                       .order_by(TechnicalNote.created_at.desc(), TechnicalNote.id.desc()))
    return {"vehicle": vehicle_full(v),
            "customer": {"id": c.id, "full_name": c.full_name, "document_type": c.document_type,
                         "document_number": c.document_number},
            "orders": _orders(db, v.id),
            "notes": [{"id": n.id, "content_html": sanitize(n.content_html), "author": author,
                       "created_at": n.created_at} for n, author in notes]}


def add_note(db: Session, vehicle_id: int, html: str, user_id: int) -> dict[str, Any]:
    if db.get(Vehicle, vehicle_id) is None:
        raise HTTPException(404, VEHICLE_NOT_FOUND)
    clean = sanitize(html)
    if not nh3.clean(clean, tags=set()).strip():
        raise HTTPException(422, "Escriba el contenido de la nota.")
    note = TechnicalNote(vehicle_id=vehicle_id, author_id=user_id, content_html=clean, created_at=ahora())
    db.add(note)
    db.flush()
    registrar(db, "technical_notes", "NOTE_ADDED", user_id, note.id, {"vehicle_id": vehicle_id})
    db.commit()
    author = db.scalar(select(User.full_name).where(User.id == user_id))
    return {"id": note.id, "content_html": clean, "author": author, "created_at": note.created_at}


# --- HU-30 ------------------------------------------------------------------------------------------
def history(db: Session, user_id: int, vehicle_id: int, page: int) -> dict[str, Any]:
    v = db.scalar(select(Vehicle).join(Customer, Customer.id == Vehicle.customer_id)
                  .where(Vehicle.id == vehicle_id, Customer.user_id == user_id))
    if v is None:  # RN-46: un vehículo ajeno se responde como inexistente
        raise HTTPException(404, "Vehículo no encontrado.")
    per_page = 20
    orders = _orders(db, v.id, delivered_only=True, limit=per_page + 1, offset=(page - 1) * per_page)
    return {"vehicle": vehicle_out(v), "orders": orders[:per_page], "page": page, "has_more": len(orders) > per_page}
