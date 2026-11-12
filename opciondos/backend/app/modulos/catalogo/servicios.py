"""Catálogo: servicios con precio y duración (HU-18) y repuestos por servicio (HU-26)."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modulos.agenda.modelos import Appointment
from app.modulos.auditoria.servicios import registrar
from app.modulos.catalogo.modelos import FaultType, Service, ServicePart
from app.modulos.inventario.modelos import Part
from app.modulos.inventario.servicios import repuestos_requeridos


def servicio_out(db: Session, s: Service) -> dict[str, Any]:
    return {"id": s.id, "code": s.code, "name": s.name, "labor_price": s.labor_price, "duration_min": s.duration_min,
            "active": s.active,
            "repuestos": [{"part_id": p.id, "sku": p.sku, "name": p.name, "quantity": q, "available": p.available,
                           "compatible_voltage_v": p.compatible_voltage_v} for p, q in repuestos_requeridos(db, s.id)]}


def listar_servicios(db: Session, todos: bool) -> list[dict[str, Any]]:
    q = select(Service).order_by(Service.name)
    if not todos:
        q = q.where(Service.active.is_(True))
    return [servicio_out(db, s) for s in db.scalars(q)]


def _servicio(db: Session, service_id: int) -> Service:
    s = db.get(Service, service_id)
    if s is None:
        raise HTTPException(404, "Servicio no encontrado")
    return s


def crear_servicio(db: Session, datos: dict[str, Any], user_id: int) -> dict[str, Any]:
    s = Service(**datos)
    db.add(s)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "Ya existe un servicio con ese código") from exc
    registrar(db, "services", "CREATE", user_id, s.id, {"code": s.code})
    db.commit()
    return servicio_out(db, s)


def editar_servicio(db: Session, service_id: int, datos: dict[str, Any], user_id: int) -> dict[str, Any]:
    s = _servicio(db, service_id)
    cambios = {k: v for k, v in datos.items() if v is not None}
    for k, v in cambios.items():
        setattr(s, k, v)
    registrar(db, "services", "UPDATE", user_id, s.id, cambios)
    db.commit()
    return servicio_out(db, s)


def definir_repuestos(db: Session, service_id: int, lineas: list[dict[str, int]], user_id: int) -> dict[str, Any]:
    """Reemplaza la lista completa; aplica solo a citas futuras (las reservas existentes no cambian)."""
    s = _servicio(db, service_id)
    ids = [l["part_id"] for l in lineas]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "El repuesto ya está en la lista")
    partes = {p.id: p for p in db.scalars(select(Part).where(Part.id.in_(ids)))}
    for pid in ids:
        if pid not in partes or not partes[pid].active:
            raise HTTPException(422, "El repuesto no existe o está inactivo")
    for sp in db.scalars(select(ServicePart).where(ServicePart.service_id == s.id)):
        db.delete(sp)
    db.flush()
    for l in lineas:
        db.add(ServicePart(service_id=s.id, part_id=l["part_id"], quantity=l["quantity"]))
    registrar(db, "services", "PARTS_UPDATE", user_id, s.id, {"repuestos": lineas})
    activas = db.scalar(select(func.count()).select_from(Appointment).where(
        Appointment.service_id == s.id, Appointment.status.in_(("CONFIRMED", "RESCHEDULED")))) or 0
    db.commit()
    salida = servicio_out(db, s)
    salida["advertencia"] = (f"Las {activas} citas ya confirmadas conservan los repuestos reservados originalmente"
                             if activas else None)
    return salida


def listar_fallas(db: Session) -> list[dict[str, Any]]:
    return [{"id": f.id, "name": f.name, "priority": f.priority, "estimated_minutes": f.estimated_minutes}
            for f in db.scalars(select(FaultType).order_by(FaultType.id))]
