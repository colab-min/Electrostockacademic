"""Reservas de repuestos (HU-19, RN-15 a RN-20). Las usan agenda (citas) y órdenes.

Bloqueo pesimista: los repuestos se leen con SELECT ... FOR UPDATE en orden de id, después de las franjas.
"""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modulos.auditoria.servicios import registrar
from app.modulos.catalogo.modelos import ServicePart
from app.modulos.inventario.modelos import InventoryMovement, Part, PartReservation


def repuestos_requeridos(db: Session, service_id: int) -> list[tuple[Part, int]]:
    filas = db.execute(select(Part, ServicePart.quantity).join(ServicePart, ServicePart.part_id == Part.id)
                       .where(ServicePart.service_id == service_id).order_by(Part.id)).all()
    return [(p, q) for p, q in filas]


def reservar_para_cita(db: Session, service_id: int, appointment_id: int, expires_at: datetime,
                       voltaje_vehiculo: int | None = None, motivo_voltaje: str | None = None,
                       user_id: int | None = None) -> list[PartReservation]:
    """Reserva todos los repuestos del servicio o ninguno. 409 si falta disponible o el voltaje no coincide."""
    ids = [p.id for p, _ in repuestos_requeridos(db, service_id)]
    partes = {p.id: p for p in db.scalars(select(Part).where(Part.id.in_(ids)).order_by(Part.id).with_for_update())}
    cantidades = dict((p.id, q) for p, q in repuestos_requeridos(db, service_id))
    for pid in ids:
        parte = partes[pid]
        if parte.available < cantidades[pid] or not parte.active:
            raise HTTPException(409, f"No tenemos {parte.name} disponible para este servicio en este momento.")
        if (voltaje_vehiculo and parte.compatible_voltage_v and parte.compatible_voltage_v != voltaje_vehiculo
                and not motivo_voltaje):
            raise HTTPException(409, f"Riesgo eléctrico: {parte.name} es de {parte.compatible_voltage_v} V y el "
                                     f"vehículo es de {voltaje_vehiculo} V. Indica un motivo para continuar.")
    reservas = []
    for pid in ids:
        partes[pid].reserved_stock += cantidades[pid]
        reserva = PartReservation(part_id=pid, appointment_id=appointment_id, quantity=cantidades[pid],
                                  status="ACTIVE", expires_at=expires_at)
        db.add(reserva)
        reservas.append(reserva)
    if motivo_voltaje:
        registrar(db, "appointments", "VOLTAGE_OVERRIDE", user_id, appointment_id, {"motivo": motivo_voltaje})
    return reservas


def liberar(db: Session, *, appointment_id: int | None = None, work_order_id: int | None = None,
            estado_final: str = "RELEASED") -> int:
    """Libera las reservas activas de una cita u orden (cancelación, expiración, inasistencia). Idempotente."""
    cond = (PartReservation.appointment_id == appointment_id) if appointment_id is not None \
        else (PartReservation.work_order_id == work_order_id)
    reservas = list(db.scalars(select(PartReservation).where(cond, PartReservation.status == "ACTIVE")))
    partes = {p.id: p for p in db.scalars(select(Part).where(Part.id.in_([r.part_id for r in reservas]))
                                          .order_by(Part.id).with_for_update())}
    for r in reservas:
        partes[r.part_id].reserved_stock -= r.quantity
        r.status = estado_final
    return len(reservas)


def extender(db: Session, appointment_id: int, expires_at: datetime) -> None:
    """Al confirmar o reprogramar, las reservas vencen en la hora de la cita más la tolerancia."""
    for r in db.scalars(select(PartReservation).where(PartReservation.appointment_id == appointment_id,
                                                       PartReservation.status == "ACTIVE")):
        r.expires_at = expires_at


def transferir_a_orden(db: Session, appointment_id: int, work_order_id: int) -> list[PartReservation]:
    """Crear la orden desde la cita transfiere sus reservas (RN-26); dejan de vencer."""
    reservas = list(db.scalars(select(PartReservation).where(PartReservation.appointment_id == appointment_id,
                                                             PartReservation.status == "ACTIVE")))
    for r in reservas:
        r.work_order_id, r.expires_at = work_order_id, None
    return reservas


# --- Repuestos y movimientos (HU-08, HU-27, HU-29) ---------------------------------------------------------

PRECIO_STOCK = "El precio debe ser mayor a cero y el stock no puede ser negativo"


def repuesto_out(p: Part) -> dict:
    return {"id": p.id, "sku": p.sku, "name": p.name, "category": p.category, "purchase_price": p.purchase_price,
            "sale_price": p.sale_price, "physical_stock": p.physical_stock, "reserved_stock": p.reserved_stock,
            "available": p.available, "min_threshold": p.min_threshold,
            "compatible_voltage_v": p.compatible_voltage_v, "active": p.active,
            "alerta": p.active and p.available <= p.min_threshold}  # RN-21: en o por debajo del umbral


def listar_repuestos(db: Session) -> list[dict]:
    return [repuesto_out(p) for p in db.scalars(select(Part).order_by(Part.sku))]


def crear_repuesto(db: Session, datos: dict, user_id: int) -> dict:
    if datos["purchase_price"] <= 0 or datos["sale_price"] <= 0 or datos["physical_stock"] < 0:
        raise HTTPException(422, PRECIO_STOCK)
    if db.scalar(select(Part.id).where(Part.sku == datos["sku"].strip())):
        raise HTTPException(409, "El código de repuesto ingresado ya existe en el inventario")
    p = Part(**{**datos, "sku": datos["sku"].strip()}, reserved_stock=0, active=True)
    db.add(p)
    db.flush()
    registrar(db, "parts", "CREATE", user_id, p.id, {"sku": p.sku, "physical_stock": p.physical_stock})
    db.commit()
    return repuesto_out(p)


def editar_repuesto(db: Session, part_id: int, datos: dict, user_id: int) -> dict:
    p = db.get(Part, part_id)
    if p is None:
        raise HTTPException(404, "Repuesto no encontrado")
    cambios = {k: v for k, v in datos.items() if v is not None}
    if any(cambios.get(k, 1) <= 0 for k in ("purchase_price", "sale_price")):
        raise HTTPException(422, PRECIO_STOCK)
    for k, v in cambios.items():
        setattr(p, k, v)
    registrar(db, "parts", "UPDATE", user_id, p.id, cambios)
    db.commit()
    return repuesto_out(p)


def registrar_movimiento(db: Session, datos: dict, user_id: int) -> dict:
    tipo, cantidad, motivo = datos["type"], datos["quantity"], (datos.get("reason") or "").strip()
    if cantidad == 0 or (tipo != "ADJUSTMENT" and cantidad < 0):
        raise HTTPException(422, "La cantidad debe ser mayor a cero")
    if tipo != "IN" and not motivo:
        raise HTTPException(422, "Indique el motivo del movimiento")
    p = db.scalar(select(Part).where(Part.id == datos["part_id"]).with_for_update())
    if p is None:
        raise HTTPException(404, "Repuesto no encontrado")
    delta = {"IN": cantidad, "WRITE_OFF": -cantidad, "ADJUSTMENT": cantidad}[tipo]
    nuevo = p.physical_stock + delta
    if nuevo < p.reserved_stock:  # RN-20
        raise HTTPException(409, f"La baja dejaría el stock físico ({max(nuevo, 0)}) por debajo de lo reservado "
                                 f"({p.reserved_stock}). Libere reservas primero.")
    p.physical_stock = nuevo
    db.add(InventoryMovement(part_id=p.id, type=tipo, quantity=delta, reason=motivo or None, user_id=user_id))
    registrar(db, "inventory_movements", tipo, user_id, p.id, {"cantidad": delta, "motivo": motivo or None})
    db.commit()
    return repuesto_out(p)


def listar_movimientos(db: Session) -> list[dict]:
    filas = db.execute(select(InventoryMovement, Part.sku, Part.name).join(Part, Part.id == InventoryMovement.part_id)
                       .order_by(InventoryMovement.id.desc()).limit(100)).all()
    return [{"id": m.id, "part_id": m.part_id, "sku": sku, "name": name, "type": m.type, "quantity": m.quantity,
             "reason": m.reason, "created_at": m.created_at} for m, sku, name in filas]
