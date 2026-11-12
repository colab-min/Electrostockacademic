"""Órdenes de trabajo: creación (HU-23, HU-03), cola (HU-04), estados (HU-05), asignación (HU-24),
repuestos y servicios (HU-09, HU-25) y seguimiento público (HU-07)."""

import math
import re
import secrets
import threading
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.modulos.agenda.modelos import Appointment, AppointmentSlot, Slot
from app.modulos.agenda.tareas import registrar_tarea
from app.modulos.auditoria.servicios import registrar
from app.modulos.catalogo.modelos import FaultType, Service
from app.modulos.clientes.modelos import Customer, Vehicle
from app.modulos.identidad.modelos import User
from app.modulos.inventario import servicios as inventario
from app.modulos.inventario.modelos import InventoryMovement, Part, PartReservation
from app.modulos.ordenes.modelos import (Sequence, WorkOrder, WorkOrderPart, WorkOrderService, WorkOrderSlot,
                                         WorkOrderStatusHistory)
from app.seguridad import CurrentUser, sha256
from app.tiempo import ahora

ETIQUETAS = {"RECEIVED": "Ingresada", "ASSIGNED": "Asignada", "DIAGNOSING": "En diagnóstico",
             "WAITING_PARTS": "Esperando repuesto", "REPAIRING": "En reparación", "FINISHED": "Finalizada",
             "PENDING_PAYMENT": "Pendiente de pago", "PAID": "Pagada", "DELIVERED": "Entregada",
             "CANCELLED": "Cancelada", "PENDING_INSTALLATION": "Pendiente de instalación"}
PUBLICAS = {"RECEIVED": "Recibido", "ASSIGNED": "Recibido", "FINISHED": "Listo para entrega",
            "PENDING_PAYMENT": "Listo para entrega", "PAID": "Listo para entrega"}
TIPOS = {"E_BIKE": "Bicicleta eléctrica", "SCOOTER": "Scooter eléctrico", "KICK_SCOOTER": "Patineta eléctrica",
         "MOTORCYCLE": "Motocicleta eléctrica", "UNICYCLE": "Monociclo eléctrico", "MICROCAR": "Microcarro eléctrico",
         "QUADRICYCLE": "Cuadriciclo eléctrico"}

RECEPCION, MECANICO, ADMIN = frozenset({"RECEPTIONIST", "ADMIN"}), frozenset({"MECHANIC"}), frozenset({"ADMIN"})
# Patrón State simple (DE-02): estado actual -> {destino: roles que pueden darlo}.
TRANSICIONES: dict[str, dict[str, frozenset[str]]] = {
    "RECEIVED": {"ASSIGNED": ADMIN, "CANCELLED": RECEPCION},
    "ASSIGNED": {"DIAGNOSING": MECANICO, "CANCELLED": RECEPCION},
    "DIAGNOSING": {"WAITING_PARTS": MECANICO, "REPAIRING": MECANICO},
    "WAITING_PARTS": {"REPAIRING": MECANICO, "PENDING_INSTALLATION": MECANICO},
    "REPAIRING": {"WAITING_PARTS": MECANICO, "FINISHED": MECANICO},
    "PENDING_INSTALLATION": {"CANCELLED": RECEPCION},  # shortcut: el reingreso (RN-55) queda fuera de la demo
    "FINISHED": {"PENDING_PAYMENT": RECEPCION},
    "PENDING_PAYMENT": {"PAID": RECEPCION},
    "PAID": {"DELIVERED": RECEPCION},
}
CERRADAS = ("DELIVERED", "CANCELLED")
TECNICOS = ("ASSIGNED", "DIAGNOSING", "WAITING_PARTS", "REPAIRING")
CITA_ACTIVA = ("HELD", "CONFIRMED", "RESCHEDULED")
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin I, O, 0 ni 1 (ADR-33)
CODIGO_RE = re.compile(r"^[A-HJ-NP-Z2-9]{10}$")
RANGO_PRIORIDAD = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, None: 3}

NO_ENCONTRADA = "No se encontró la orden."
MODIFICADA = "La orden fue modificada por otro usuario, actualice la vista"
ERROR_SECUENCIA = "Error al generar la orden de trabajo, vuelva a intentarlo"

_cupo_liberado = threading.Event()


def marcar_cupo_liberado() -> None:
    """Avisa a la tarea `ubicar_cola` que se liberó capacidad (RN-54). Otros módulos también pueden llamarla."""
    _cupo_liberado.set()


# ---------------------------------------------------------------- lectura

def _bloquear(db: Session, order_id: int) -> WorkOrder:
    wo = db.scalar(select(WorkOrder).where(WorkOrder.id == order_id).with_for_update())
    if wo is None:
        raise HTTPException(404, NO_ENCONTRADA)
    return wo


def orden_para(db: Session, order_id: int, user: CurrentUser, lock: bool = False) -> WorkOrder:
    """El mecánico solo ve sus órdenes; una ajena se responde como no encontrada y queda en la bitácora (RN-29)."""
    wo = _bloquear(db, order_id) if lock else db.get(WorkOrder, order_id)
    if wo is None:
        raise HTTPException(404, NO_ENCONTRADA)
    if user.role == "MECHANIC" and wo.mechanic_id != user.id:
        db.rollback()
        registrar(db, "work_orders", "ACCESS_DENIED", user.id, order_id, {"motivo": "orden de otro mecánico"})
        db.commit()
        raise HTTPException(404, NO_ENCONTRADA)
    return wo


def resumen(db: Session, wo: WorkOrder) -> dict:
    v = db.get(Vehicle, wo.vehicle_id)
    assert v
    mec = db.get(User, wo.mechanic_id) if wo.mechanic_id else None
    servicios = db.execute(select(Service.name).join(WorkOrderService, WorkOrderService.service_id == Service.id)
                           .where(WorkOrderService.work_order_id == wo.id)).scalars().all()
    return {"id": wo.id, "number": wo.number, "status": wo.status, "status_label": ETIQUETAS[wo.status],
            "priority": wo.priority, "origin": wo.origin, "intake_reason": wo.intake_reason,
            "mechanic_id": wo.mechanic_id, "mechanic_name": mec.full_name if mec else None,
            "queue_position": wo.queue_position, "estimated_delivery_at": wo.estimated_delivery_at,
            "created_at": wo.created_at, "version": wo.version, "services": list(servicios),
            "vehicle": {"id": v.id, "type": v.type, "type_label": TIPOS[v.type], "brand": v.brand, "model": v.model,
                        "serial_number": v.serial_number, "plate": v.plate, "nominal_voltage_v": v.nominal_voltage_v}}


def detalle(db: Session, wo: WorkOrder) -> dict:
    out = resumen(db, wo)
    out["diagnosis"] = wo.diagnosis
    out["service_lines"] = [{"service_id": s.id, "name": s.name, "applied_price": p} for s, p in db.execute(
        select(Service, WorkOrderService.applied_price).join(WorkOrderService, WorkOrderService.service_id == Service.id)
        .where(WorkOrderService.work_order_id == wo.id))]
    out["parts"] = [{"id": line.id, "part_id": p.id, "sku": p.sku, "name": p.name, "quantity": line.quantity,
                     "unit_price": line.unit_price, "status": line.status}
                    for line, p in db.execute(select(WorkOrderPart, Part).join(Part, Part.id == WorkOrderPart.part_id)
                                              .where(WorkOrderPart.work_order_id == wo.id).order_by(WorkOrderPart.id))]
    out["history"] = [{"from_status": h.from_status, "to_status": h.to_status, "label": ETIQUETAS.get(h.to_status, h.to_status),
                       "user_name": u.full_name if u else None, "reason": h.reason, "created_at": h.created_at}
                      for h, u in db.execute(select(WorkOrderStatusHistory, User)
                                             .outerjoin(User, User.id == WorkOrderStatusHistory.user_id)
                                             .where(WorkOrderStatusHistory.work_order_id == wo.id)
                                             .order_by(WorkOrderStatusHistory.created_at, WorkOrderStatusHistory.id))]
    return out


def listar(db: Session, estado: str | None) -> list[dict]:
    q = select(WorkOrder).order_by(WorkOrder.created_at)
    q = q.where(WorkOrder.status == estado) if estado else q.where(WorkOrder.status.notin_(CERRADAS))
    ordenes = _ordenar_cola(db, list(db.scalars(q)))  # prioridad y llegada (AD-02)
    return [resumen(db, wo) for wo in ordenes]


def mias(db: Session, user: CurrentUser) -> list[dict]:
    q = select(WorkOrder).where(WorkOrder.mechanic_id == user.id, WorkOrder.status.in_(TECNICOS))
    out = []
    for wo in _ordenar_cola(db, list(db.scalars(q))):
        r = resumen(db, wo)
        r["transitions"] = transiciones(wo, user.role)
        out.append(r)
    return out


def transiciones(wo: WorkOrder, rol: str) -> list[dict]:
    return [{"to_status": d, "label": ETIQUETAS[d]} for d, roles in TRANSICIONES.get(wo.status, {}).items() if rol in roles]


# ---------------------------------------------------------------- máquina de estados

def cambiar_estado(db: Session, wo: WorkOrder, destino: str, user: CurrentUser, reason: str | None = None,
                   version: int | None = None) -> None:
    """Valida contra DE-02, controla la versión y registra historial y bitácora (RN-27)."""
    if version is not None and version != wo.version:
        raise HTTPException(409, MODIFICADA)
    pasos = TRANSICIONES.get(wo.status, {})
    if user.role not in pasos.get(destino, ()):
        validos = [ETIQUETAS[d] for d, roles in pasos.items() if user.role in roles] or [ETIQUETAS[d] for d in pasos]
        raise HTTPException(409, f"Esta orden no puede pasar de {ETIQUETAS[wo.status]} a "
                                 f"{ETIQUETAS.get(destino, destino)}. Pasos válidos: {', '.join(validos) or 'ninguno'}.")
    if destino == "FINISHED":
        pendientes = db.scalars(select(Part.name).join(WorkOrderPart, WorkOrderPart.part_id == Part.id)
                                .where(WorkOrderPart.work_order_id == wo.id, WorkOrderPart.status == "RESERVED")).all()
        if pendientes:
            raise HTTPException(409, "No se puede finalizar: instale o retire estos repuestos reservados: "
                                     f"{', '.join(pendientes)}.")
    if destino == "PENDING_INSTALLATION" and not (reason or "").strip():
        raise HTTPException(422, "Indique el motivo y el repuesto esperado.")
    if destino == "CANCELLED" and wo.status == "PENDING_INSTALLATION" and not (reason or "").strip():
        raise HTTPException(422, "Indique el motivo de la cancelación.")
    anterior = wo.status
    wo.status, wo.version = destino, wo.version + 1
    db.add(WorkOrderStatusHistory(work_order_id=wo.id, from_status=anterior, to_status=destino, user_id=user.id,
                                  reason=reason, created_at=ahora()))
    registrar(db, "work_orders", "STATUS_CHANGE", user.id, wo.id, {"from": anterior, "to": destino, "reason": reason})
    if destino in ("CANCELLED", "PENDING_INSTALLATION"):
        _liberar_franjas(db, wo)
    if destino == "CANCELLED":
        inventario.liberar(db, work_order_id=wo.id)
        for line in db.scalars(select(WorkOrderPart).where(WorkOrderPart.work_order_id == wo.id,
                                                           WorkOrderPart.status == "RESERVED")):
            line.status = "RETURNED"
        if wo.queue_position is not None:
            wo.queue_position = None
            _renumerar_cola(db)


def avanzar(db: Session, order_id: int, user: CurrentUser, destino: str, version: int, reason: str | None) -> dict:
    wo = orden_para(db, order_id, user, lock=True)
    cambiar_estado(db, wo, destino, user, reason, version)
    db.commit()
    if destino == "PENDING_INSTALLATION":
        marcar_cupo_liberado()
    return detalle(db, wo)


def cancelar(db: Session, order_id: int, user: CurrentUser, reason: str | None, version: int | None) -> dict:
    wo = _bloquear(db, order_id)
    cambiar_estado(db, wo, "CANCELLED", user, reason, version)
    db.commit()
    marcar_cupo_liberado()
    return resumen(db, wo)


def _liberar_franjas(db: Session, wo: WorkOrder) -> None:
    """Devuelve el cupo de las franjas de la orden. Las filas de work_order_slots se conservan como historia."""
    ids = db.scalars(select(WorkOrderSlot.slot_id).where(WorkOrderSlot.work_order_id == wo.id)).all()
    for s in db.scalars(select(Slot).where(Slot.id.in_(ids)).order_by(Slot.id).with_for_update()):
        s.booked_count = max(0, s.booked_count - 1)


# ---------------------------------------------------------------- creación

def _orden_activa(db: Session, vehicle_id: int) -> None:
    activa = db.scalar(select(WorkOrder.number).where(WorkOrder.vehicle_id == vehicle_id,
                                                      WorkOrder.status.notin_(CERRADAS)))
    if activa:
        raise HTTPException(409, f"El vehículo ya tiene una orden activa (N° {activa}) en proceso")


def _nueva_orden(db: Session, user: CurrentUser, **campos: object) -> tuple[WorkOrder, str]:
    """Número correlativo atómico (RN-24) y código de seguimiento entregado una sola vez (RN-25)."""
    seq = db.scalar(select(Sequence).where(Sequence.name == "WO").with_for_update())
    if seq is None:
        raise HTTPException(500, ERROR_SECUENCIA)
    seq.value += 1
    codigo = "".join(secrets.choice(ALFABETO) for _ in range(10))
    wo = WorkOrder(number=f"OT-{seq.value:06d}", tracking_code_hash=sha256(codigo), status="RECEIVED", version=1,
                   created_at=ahora(), **campos)
    db.add(wo)
    db.flush()
    db.add(WorkOrderStatusHistory(work_order_id=wo.id, from_status=None, to_status="RECEIVED", user_id=user.id,
                                  created_at=ahora()))
    registrar(db, "work_orders", "CREATE", user.id, wo.id, {"number": wo.number, "origin": wo.origin})
    return wo, codigo


def _confirmar(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, ERROR_SECUENCIA) from exc


def citas_del_dia(db: Session, q: str | None) -> list[dict]:
    hoy = ahora().date()
    filas = db.execute(select(Appointment, Vehicle, Customer, Service)
                       .join(Vehicle, Vehicle.id == Appointment.vehicle_id)
                       .join(Customer, Customer.id == Appointment.customer_id)
                       .join(Service, Service.id == Appointment.service_id)
                       .where(Appointment.status.in_(("CONFIRMED", "RESCHEDULED")),
                              Appointment.starts_at >= datetime.combine(hoy, time()),
                              Appointment.starts_at < datetime.combine(hoy + timedelta(days=1), time()))
                       .order_by(Appointment.starts_at)).all()
    texto = (q or "").strip().upper()
    return [{"id": a.id, "code": a.code, "starts_at": a.starts_at, "status": a.status,
             "service": {"id": s.id, "name": s.name, "duration_min": s.duration_min},
             "customer": {"full_name": c.full_name},
             "vehicle": {"id": v.id, "type": v.type, "type_label": TIPOS[v.type], "brand": v.brand, "model": v.model,
                         "serial_number": v.serial_number, "plate": v.plate}}
            for a, v, c, s in filas
            if not texto or texto in a.code.upper() or texto in v.serial_number.upper() or texto == (v.plate or "").upper()]


def crear_desde_cita(db: Session, appointment_id: int, intake_reason: str | None, user: CurrentUser) -> dict:
    cita = db.scalar(select(Appointment).where(Appointment.id == appointment_id).with_for_update())
    if cita is None:
        raise HTTPException(404, "No se encontró una cita con ese código o serie.")
    if cita.status not in ("CONFIRMED", "RESCHEDULED"):
        raise HTTPException(409, "La cita no está vigente. Registre el ingreso sin cita.")
    if cita.starts_at.date() != ahora().date():
        raise HTTPException(409, f"La cita es para el {cita.starts_at:%d/%m/%Y %H:%M}; la orden se crea el día de la cita.")
    _orden_activa(db, cita.vehicle_id)
    # Franjas primero y después repuestos (orden fijo de bloqueo).
    slot_ids = db.scalars(select(AppointmentSlot.slot_id).where(AppointmentSlot.appointment_id == cita.id)).all()
    franjas = list(db.scalars(select(Slot).where(Slot.id.in_(slot_ids)).order_by(Slot.id).with_for_update()))
    servicio = db.get(Service, cita.service_id)
    assert servicio
    wo, codigo = _nueva_orden(db, user, vehicle_id=cita.vehicle_id, appointment_id=cita.id, origin="APPOINTMENT",
                              intake_reason=(intake_reason or "").strip() or servicio.name,
                              estimated_delivery_at=cita.starts_at + timedelta(minutes=servicio.duration_min))
    for s in franjas:  # se copian sin ocupar más cupo (RN-26)
        db.add(WorkOrderSlot(work_order_id=wo.id, slot_id=s.id))
    db.add(WorkOrderService(work_order_id=wo.id, service_id=servicio.id, applied_price=servicio.labor_price))
    for r in inventario.transferir_a_orden(db, cita.id, wo.id):
        parte = db.get(Part, r.part_id)
        assert parte
        db.add(WorkOrderPart(work_order_id=wo.id, part_id=r.part_id, reservation_id=r.id, quantity=r.quantity,
                             unit_price=parte.sale_price, status="RESERVED"))
    cita.status = "ATTENDED"
    registrar(db, "appointments", "ATTENDED", user.id, cita.id, {"work_order": wo.number})
    _confirmar(db)
    return {**resumen(db, wo), "tracking_code": codigo}


def ingreso_sin_cita(db: Session, vehicle_id: int, fault_type_id: int | None, service_id: int | None,
                     intake_reason: str | None, user: CurrentUser) -> dict:
    servicio = db.get(Service, service_id) if service_id else None
    if servicio is None or not servicio.active:
        raise HTTPException(422, "Seleccione el servicio")
    falla = db.get(FaultType, fault_type_id) if fault_type_id else None
    if falla is None:
        raise HTTPException(422, "Seleccione el tipo de falla")
    if db.get(Vehicle, vehicle_id) is None:
        raise HTTPException(404, "No se encontró un vehículo con esa serie, placa o documento.")
    _orden_activa(db, vehicle_id)
    cita = db.scalar(select(Appointment).where(Appointment.vehicle_id == vehicle_id,
                                               Appointment.status.in_(CITA_ACTIVA)).order_by(Appointment.starts_at))
    if cita:
        aviso = "" if cita.starts_at.date() == ahora().date() else " La hora de la cita no corresponde a hoy."
        raise HTTPException(409, f"El vehículo tiene la cita {cita.code} ({cita.starts_at:%d/%m/%Y %H:%M}). "
                                 f"Cree la orden desde esa cita.{aviso}")
    now = ahora()
    franjas = _franjas(db, now.date(), desde=now, lock=True)  # franjas antes que la secuencia
    wo, codigo = _nueva_orden(db, user, vehicle_id=vehicle_id, origin="WALK_IN", fault_type_id=falla.id,
                              priority=falla.priority, intake_reason=(intake_reason or "").strip() or falla.name)
    db.add(WorkOrderService(work_order_id=wo.id, service_id=servicio.id, applied_price=servicio.labor_price))
    db.flush()
    if not _ocupar_si_cabe(db, wo, now.date(), franjas, servicio.duration_min):
        wo.queue_position = 0
        _renumerar_cola(db)
    _confirmar(db)
    return {**resumen(db, wo), "tracking_code": codigo, "hora_estimada": horas_estimadas(db).get(wo.id)}


# ---------------------------------------------------------------- ubicación y cola (RN-33, RN-35, RN-54)

def _franjas(db: Session, dia: date, desde: datetime | None = None, lock: bool = False) -> dict[int, Slot]:
    q = select(Slot).where(Slot.slot_date == dia).order_by(Slot.id)
    if lock:
        q = q.with_for_update()
    return {s.start_time.hour: s for s in db.scalars(q) if desde is None or datetime.combine(dia, s.start_time) >= desde}


def _libres(franjas: dict[int, Slot]) -> dict[int, int]:
    return {h: 0 if s.blocked else s.capacity - s.booked_count for h, s in franjas.items()}


def _primer_hueco(libres: dict[int, int], n: int) -> int | None:
    """Primera hora desde la que caben n franjas consecutivas con cupo, sin tocar las ocupadas por citas."""
    return next((h for h in sorted(libres) if all(libres.get(h + i, 0) > 0 for i in range(n))), None)


def _duracion(db: Session, wo: WorkOrder) -> int:
    return sum(db.scalars(select(Service.duration_min).join(WorkOrderService, WorkOrderService.service_id == Service.id)
                          .where(WorkOrderService.work_order_id == wo.id))) or 60


def _ocupar_si_cabe(db: Session, wo: WorkOrder, dia: date, franjas: dict[int, Slot], minutos: int) -> bool:
    n = max(1, math.ceil(minutos / 60))
    h = _primer_hueco(_libres(franjas), n)
    if h is None:
        return False
    for i in range(n):
        franjas[h + i].booked_count += 1
        db.add(WorkOrderSlot(work_order_id=wo.id, slot_id=franjas[h + i].id))
    wo.queue_position = None
    wo.estimated_delivery_at = datetime.combine(dia, time(h)) + timedelta(minutes=minutos)
    return True


def _clave_cola(db: Session, wo: WorkOrder) -> tuple:
    """Prioridad y llegada; una falla de menos de 15 min va primero dentro de su prioridad, nunca antes de una más alta."""
    falla = db.get(FaultType, wo.fault_type_id) if wo.fault_type_id else None
    corta = falla is not None and falla.estimated_minutes < 15
    return RANGO_PRIORIDAD.get(wo.priority, 3), 0 if corta else 1, wo.created_at, wo.id


def _ordenar_cola(db: Session, ordenes: list[WorkOrder]) -> list[WorkOrder]:
    return sorted(ordenes, key=lambda wo: _clave_cola(db, wo))


def _en_cola(db: Session, lock: bool = False) -> list[WorkOrder]:
    q = select(WorkOrder).where(WorkOrder.queue_position.isnot(None), WorkOrder.status.notin_(CERRADAS))
    if lock:
        q = q.with_for_update(skip_locked=True)
    return _ordenar_cola(db, list(db.scalars(q)))


def _renumerar_cola(db: Session) -> None:
    db.flush()
    for i, wo in enumerate(_en_cola(db), start=1):
        wo.queue_position = i


def _dias_habiles(desde: date, cantidad: int) -> list[date]:
    dias, d = [], desde
    while len(dias) < cantidad:
        if d.weekday() != 6:
            dias.append(d)
        d += timedelta(days=1)
    return dias


def horas_estimadas(db: Session) -> dict[int, datetime | None]:
    """Hora estimada de cada orden en cola: simula la ubicación en orden de cola sobre la capacidad libre."""
    now = ahora()
    libres = {d: _libres(_franjas(db, d, desde=now if d == now.date() else None)) for d in _dias_habiles(now.date(), 7)}
    out: dict[int, datetime | None] = {}
    for wo in _en_cola(db):
        n, out[wo.id] = max(1, math.ceil(_duracion(db, wo) / 60)), None
        for d, mapa in libres.items():
            h = _primer_hueco(mapa, n)
            if h is not None:
                for i in range(n):
                    mapa[h + i] -= 1
                out[wo.id] = datetime.combine(d, time(h))
                break
    return out


def cola(db: Session) -> list[dict]:
    estimadas = horas_estimadas(db)
    out = []
    for wo in _en_cola(db):
        falla = db.get(FaultType, wo.fault_type_id) if wo.fault_type_id else None
        out.append({**resumen(db, wo), "fault_name": falla.name if falla else None, "hora_estimada": estimadas.get(wo.id)})
    return out


@registrar_tarea("ubicar_cola")
def ubicar_cola(db: Session) -> None:
    """RN-54: al liberarse cupo ubica la cola desde la hora actual; al cierre, en el siguiente día hábil."""
    now = ahora()
    cierre = now.hour > config.LAST_SLOT_HOUR
    if not (_cupo_liberado.is_set() or cierre):
        return
    _cupo_liberado.clear()
    ordenes = _en_cola(db, lock=True)
    if not ordenes:
        return
    dia = _dias_habiles(now.date() + timedelta(days=1), 1)[0] if cierre else now.date()
    franjas = _franjas(db, dia, desde=None if cierre else now, lock=True)
    for wo in ordenes:
        if _ocupar_si_cabe(db, wo, dia, franjas, _duracion(db, wo)):
            registrar(db, "work_orders", "QUEUE_PLACED", None, wo.id, {"day": dia.isoformat()})
    _renumerar_cola(db)


# ---------------------------------------------------------------- asignación (HU-24)

def asignar(db: Session, order_id: int, mechanic_id: int, version: int | None, user: CurrentUser) -> dict:
    wo = _bloquear(db, order_id)
    if version is not None and version != wo.version:
        raise HTTPException(409, "La orden ha sido modificada por otro usuario, por favor actualice la página")
    mec = db.get(User, mechanic_id)
    if mec is None or mec.role != "MECHANIC" or not mec.active:
        raise HTTPException(409, "El mecánico seleccionado no se encuentra activo o disponible")
    anterior = wo.mechanic_id
    if wo.status == "RECEIVED":
        cambiar_estado(db, wo, "ASSIGNED", user)
    elif wo.status in TECNICOS:
        wo.version += 1  # reasignación sin cambiar el estado
    else:
        raise HTTPException(409, f"No se puede asignar una orden {ETIQUETAS[wo.status]}.")
    wo.mechanic_id = mechanic_id
    registrar(db, "work_orders", "ASSIGN" if anterior is None else "REASSIGN", user.id, wo.id,
              {"from": anterior, "to": mechanic_id})
    db.commit()
    return resumen(db, wo)


# ---------------------------------------------------------------- trabajo del mecánico

EDITABLES = ("DIAGNOSING", "WAITING_PARTS", "REPAIRING")


def diagnosticar(db: Session, order_id: int, texto: str, version: int, user: CurrentUser) -> dict:
    wo = orden_para(db, order_id, user, lock=True)
    if version != wo.version:
        raise HTTPException(409, MODIFICADA)
    if wo.status not in EDITABLES:
        raise HTTPException(409, f"No se puede registrar el diagnóstico en una orden {ETIQUETAS[wo.status]}.")
    wo.diagnosis, wo.version = texto.strip(), wo.version + 1
    registrar(db, "work_orders", "DIAGNOSIS", user.id, wo.id, {"at": ahora().isoformat()})
    db.commit()
    return detalle(db, wo)


def agregar_repuesto(db: Session, order_id: int, part_id: int, cantidad: int, motivo: str | None,
                     user: CurrentUser) -> dict:
    wo = orden_para(db, order_id, user, lock=True)
    if wo.status not in EDITABLES:
        raise HTTPException(409, f"No se pueden agregar repuestos a una orden {ETIQUETAS[wo.status]}.")
    parte = db.scalar(select(Part).where(Part.id == part_id).with_for_update())
    if parte is None or not parte.active:
        raise HTTPException(404, "No se encontró el repuesto.")
    if not parte.sale_price or parte.sale_price <= 0:
        raise HTTPException(409, "No se pudo agregar el repuesto por un error en el precio del catálogo, "
                                 "contacte al Administrador")
    if cantidad > parte.available:
        raise HTTPException(409, f"Cantidad solicitada supera el stock disponible (Disponible: {parte.available})")
    v = db.get(Vehicle, wo.vehicle_id)
    assert v
    if parte.compatible_voltage_v and parte.compatible_voltage_v != v.nominal_voltage_v and not (motivo or "").strip():
        raise HTTPException(409, f"Riesgo eléctrico: {parte.name} es de {parte.compatible_voltage_v} V y el vehículo "
                                 f"es de {v.nominal_voltage_v} V. Indique un motivo para continuar.")
    parte.reserved_stock += cantidad
    reserva = PartReservation(part_id=parte.id, work_order_id=wo.id, quantity=cantidad, status="ACTIVE")
    db.add(reserva)
    db.flush()
    db.add(WorkOrderPart(work_order_id=wo.id, part_id=parte.id, reservation_id=reserva.id, quantity=cantidad,
                         unit_price=parte.sale_price, status="RESERVED"))
    wo.version += 1
    registrar(db, "work_orders", "PART_ADD", user.id, wo.id,
              {"part": parte.sku, "quantity": cantidad, "voltage_reason": motivo})
    db.commit()
    return detalle(db, wo)


def _linea(db: Session, wo: WorkOrder, line_id: int) -> tuple[WorkOrderPart, Part]:
    line = db.scalar(select(WorkOrderPart).where(WorkOrderPart.id == line_id, WorkOrderPart.work_order_id == wo.id)
                     .with_for_update())
    if line is None or line.status != "RESERVED":
        raise HTTPException(409, "La línea ya no está reservada.")
    parte = db.scalar(select(Part).where(Part.id == line.part_id).with_for_update())
    assert parte
    return line, parte


def instalar_repuesto(db: Session, order_id: int, line_id: int, user: CurrentUser) -> dict:
    """HU-09: instalar descuenta físico y reservado en la misma transacción."""
    wo = orden_para(db, order_id, user, lock=True)
    if wo.status not in EDITABLES:
        raise HTTPException(409, f"No se pueden instalar repuestos en una orden {ETIQUETAS[wo.status]}.")
    line, parte = _linea(db, wo, line_id)
    reserva = db.get(PartReservation, line.reservation_id) if line.reservation_id else None
    if reserva is not None and reserva.status == "ACTIVE":
        parte.reserved_stock -= line.quantity
        reserva.status = "CONSUMED"
    parte.physical_stock -= line.quantity
    line.status = "INSTALLED"
    wo.version += 1
    db.add(InventoryMovement(part_id=parte.id, type="CONSUMPTION", quantity=-line.quantity, reason=wo.number,
                             user_id=user.id))  # delta con signo, como los movimientos de inventario
    registrar(db, "inventory_movements", "CONSUMPTION", user.id, parte.id,
              {"cantidad": -line.quantity, "motivo": wo.number})
    db.commit()
    return detalle(db, wo)


def retirar_repuesto(db: Session, order_id: int, line_id: int, user: CurrentUser) -> dict:
    wo = orden_para(db, order_id, user, lock=True)
    line, parte = _linea(db, wo, line_id)
    reserva = db.get(PartReservation, line.reservation_id) if line.reservation_id else None
    if reserva is not None and reserva.status == "ACTIVE":
        parte.reserved_stock -= line.quantity
        reserva.status = "RELEASED"
    line.status = "RETURNED"
    wo.version += 1
    registrar(db, "work_orders", "PART_RETURN", user.id, wo.id, {"part": parte.sku, "quantity": line.quantity})
    db.commit()
    return detalle(db, wo)


def agregar_servicio(db: Session, order_id: int, service_id: int, user: CurrentUser) -> dict:
    wo = orden_para(db, order_id, user, lock=True)
    if wo.status not in EDITABLES:
        raise HTTPException(409, f"No se pueden agregar servicios a una orden {ETIQUETAS[wo.status]}.")
    servicio = db.get(Service, service_id)
    if servicio is None or not servicio.active:
        raise HTTPException(409, "El servicio no está activo.")
    if db.get(WorkOrderService, (wo.id, servicio.id)):
        raise HTTPException(409, "El servicio ya está en la orden.")
    db.add(WorkOrderService(work_order_id=wo.id, service_id=servicio.id, applied_price=servicio.labor_price))
    wo.estimated_delivery_at = max(wo.estimated_delivery_at or ahora(), ahora()) + timedelta(minutes=servicio.duration_min)
    wo.version += 1
    registrar(db, "work_orders", "SERVICE_ADD", user.id, wo.id, {"service": servicio.code})
    db.commit()
    return detalle(db, wo)


# ---------------------------------------------------------------- seguimiento público (HU-07)

def seguimiento(db: Session, codigo: str) -> dict:
    codigo = codigo.strip().upper()
    wo = db.scalar(select(WorkOrder).where(WorkOrder.tracking_code_hash == sha256(codigo))) \
        if CODIGO_RE.fullmatch(codigo) else None  # un formato inválido ni siquiera se busca
    if wo is None:
        raise HTTPException(404, "No encontramos información con ese código. Verifica e intenta de nuevo.")
    v = db.get(Vehicle, wo.vehicle_id)
    assert v
    linea: list[dict] = []
    for h in db.scalars(select(WorkOrderStatusHistory).where(WorkOrderStatusHistory.work_order_id == wo.id)
                        .order_by(WorkOrderStatusHistory.created_at, WorkOrderStatusHistory.id)):
        titulo = PUBLICAS.get(h.to_status, ETIQUETAS.get(h.to_status, h.to_status))
        if not linea or linea[-1]["titulo"] != titulo:  # estados con la misma etiqueta pública son un hito
            linea.append({"titulo": titulo, "fecha": h.created_at})
    # Lista blanca: nada personal, ni costos, ni mecánico, ni serie.
    return {"tipo": TIPOS[v.type], "modelo": f"{v.brand} {v.model}", "estado": wo.status,
            "estado_publico": PUBLICAS.get(wo.status, ETIQUETAS[wo.status]), "linea_tiempo": linea,
            "entrega_estimada": wo.estimated_delivery_at if wo.status not in CERRADAS else None}
