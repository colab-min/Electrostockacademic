"""Agenda: agendar con retención de 5 min (HU-01, HU-19), reprogramar y cancelar (HU-11), capacidad y bloqueos
(HU-02), recordatorios (HU-12) y tareas de liberación automática (HU-28).

Concurrencia: primero la cita (o el vehículo), después las franjas con FOR UPDATE ordenado por id y al final los
repuestos (lo hace `inventario.servicios`). Cada operación es una transacción: un HTTPException deja todo sin aplicar.
"""

import logging
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app import config
from app.modulos.agenda.modelos import Appointment, AppointmentSlot, Notification, Slot
from app.modulos.agenda.tareas import registrar_tarea
from app.modulos.auditoria.servicios import registrar
from app.modulos.catalogo.modelos import Service
from app.modulos.clientes.modelos import Customer, Vehicle
from app.modulos.inventario import servicios as inventario
from app.modulos.inventario.modelos import Part, PartReservation
from app.modulos.ordenes.modelos import WorkOrder
from app.seguridad import CurrentUser
from app.tiempo import ahora

log = logging.getLogger("agenda")
ACTIVAS = ("HELD", "CONFIRMED", "RESCHEDULED")
VIGENTES = ("CONFIRMED", "RESCHEDULED")
CAPACIDAD = 3  # shortcut: bahías activas fijas (semilla), pasar a una tabla de parámetros si cambia por taller
DIAS_GENERADOS = 30
FUERA_VENTANA = ("Ya no es posible cancelar: falta menos de 1 hora para tu cita. Si no asistes, la cita se libera "
                 "sola 15 minutos después de su hora.")
EXPIRO = "Tu reserva expiró"
NO_VIGENTE = "Esta cita ya no está vigente."


# --- Utilidades ------------------------------------------------------------------------------------------------

def _n_franjas(servicio: Service) -> int:
    return -(-servicio.duration_min // 60)  # RN-03: redondeo hacia arriba


def _hora12(h: int) -> str:
    return f"{(h - 1) % 12 + 1}:00 {'a. m.' if h < 12 else 'p. m.'}"


def _libre(s: Slot) -> bool:
    return not s.blocked and s.booked_count < s.capacity


def _inicios(por_hora: dict[int, Slot], n: int, fecha: date, now: datetime) -> list[int]:
    """Horas de inicio donde caben las n franjas consecutivas, libres y en el futuro."""
    return [h for h in sorted(por_hora) if datetime.combine(fecha, time(h)) > now
            and all(h + i in por_hora and _libre(por_hora[h + i]) for i in range(n))]


def _franjas_rango(db: Session, desde: date, hasta: date) -> dict[date, dict[int, Slot]]:
    dias: dict[date, dict[int, Slot]] = {}
    for s in db.scalars(select(Slot).where(Slot.slot_date.between(desde, hasta))):
        dias.setdefault(s.slot_date, {})[s.start_time.hour] = s
    return dias


def _servicio(db: Session, service_id: int) -> Service:
    s = db.get(Service, service_id)
    if s is None or not s.active:
        raise HTTPException(404, "Servicio no disponible")
    return s


def _cliente(db: Session, user_id: int) -> Customer:
    c = db.scalar(select(Customer).where(Customer.user_id == user_id))
    if c is None:
        raise HTTPException(404, "Cliente no encontrado")
    return c


def _sugerencia(db: Session, n: int, fecha: date, hora: int) -> str:
    """RN-09: siguiente inicio disponible del día o de los días hábiles siguientes."""
    now = ahora()
    dias = _franjas_rango(db, fecha, fecha + timedelta(days=14))
    for d in sorted(dias):
        for h in _inicios(dias[d], n, d, now):
            if d > fecha or h > hora:
                cuando = f"las {_hora12(h)}" if d == fecha else f"el {d:%d/%m/%Y} a las {_hora12(h)}"
                return f"Alguien acaba de tomar este cupo. Te sugerimos {cuando}"
    return "Alguien acaba de tomar este cupo. Elige otro día."


def _bloquear_franjas(db: Session, ids: list[int], fecha: date | None = None, horas: list[int] | None = None
                      ) -> list[Slot]:
    cond = Slot.id.in_(ids)
    if fecha is not None and horas:
        cond = or_(cond, (Slot.slot_date == fecha) & Slot.start_time.in_([time(h) for h in horas]))
    return list(db.scalars(select(Slot).where(cond).order_by(Slot.id).with_for_update()))


def _ids_franjas(db: Session, appointment_id: int) -> list[int]:
    return list(db.scalars(select(AppointmentSlot.slot_id).where(AppointmentSlot.appointment_id == appointment_id)))


def cita_out(db: Session, a: Appointment) -> dict[str, Any]:
    srv, veh = db.get(Service, a.service_id), db.get(Vehicle, a.vehicle_id)
    assert srv and veh
    limite = a.starts_at - timedelta(minutes=config.CHANGE_WINDOW_MINUTES)
    repuestos = db.execute(select(Part.name, PartReservation.quantity).join(Part, Part.id == PartReservation.part_id)
                           .where(PartReservation.appointment_id == a.id, PartReservation.status == "ACTIVE")).all()
    return {"id": a.id, "code": a.code, "status": a.status, "starts_at": a.starts_at,
            "hold_expires_at": a.hold_expires_at, "limite_cambio": limite,
            "puede_cambiar": a.status in VIGENTES and ahora() < limite,
            "service": {"id": srv.id, "name": srv.name, "duration_min": srv.duration_min,
                        "labor_price": srv.labor_price},
            "vehicle": {"id": veh.id, "serial_number": veh.serial_number, "plate": veh.plate, "brand": veh.brand,
                        "model": veh.model},
            "repuestos": [{"name": n, "quantity": q} for n, q in repuestos]}


def _mi_cita(db: Session, user: CurrentUser, appointment_id: int) -> Appointment:
    """Cita del cliente con bloqueo de fila; una cita ajena se responde como no encontrada (HU-10)."""
    a = db.scalar(select(Appointment).join(Customer, Customer.id == Appointment.customer_id)
                  .where(Appointment.id == appointment_id, Customer.user_id == user.id).with_for_update())
    if a is None:
        raise HTTPException(404, "Cita no encontrada")
    return a


def _liberar_cita(db: Session, a: Appointment, estado: str, user_id: int | None = None) -> None:
    """Pasa la cita a `estado` y devuelve cupos y repuestos (RN-19). Llamar con la cita bloqueada."""
    for s in _bloquear_franjas(db, _ids_franjas(db, a.id)):
        s.booked_count = max(0, s.booked_count - 1)
    inventario.liberar(db, appointment_id=a.id, estado_final="EXPIRED" if estado == "EXPIRED" else "RELEASED")
    registrar(db, "appointments", estado, user_id, a.id, {"from": a.status})
    a.status = estado


def _ventana(a: Appointment) -> None:
    if a.starts_at - ahora() < timedelta(minutes=config.CHANGE_WINDOW_MINUTES):
        raise HTTPException(409, FUERA_VENTANA)


# --- Consultas del asistente (no apartan nada) -----------------------------------------------------------------

def disponibilidad(db: Session, service_id: int, mes: str) -> dict[str, Any]:
    srv = _servicio(db, service_id)
    y, m = map(int, mes.split("-"))
    primero = date(y, m, 1)
    ultimo = (primero + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    repuestos_ok = all(p.active and p.available >= q for p, q in inventario.repuestos_requeridos(db, srv.id))
    now, n, dias = ahora(), _n_franjas(srv), {}
    for d, por_hora in _franjas_rango(db, max(primero, now.date()), ultimo).items():
        if all(s.blocked for s in por_hora.values()):
            dias[d.isoformat()] = "bloqueado"
        elif repuestos_ok and _inicios(por_hora, n, d, now):
            dias[d.isoformat()] = "disponible"
        else:
            dias[d.isoformat()] = "sin-cupo"
    return {"dias": dias, "repuestos_ok": repuestos_ok}


def franjas(db: Session, service_id: int, fecha: date) -> list[dict[str, Any]]:
    srv = _servicio(db, service_id)
    por_hora = _franjas_rango(db, fecha, fecha).get(fecha, {})
    inicios = set(_inicios(por_hora, _n_franjas(srv), fecha, ahora()))
    return [{"id": s.id, "hora": f"{h:02d}:00", "ocupados": s.booked_count, "capacidad": s.capacity,
             "estado": "libre" if h in inicios else ("bloqueado" if s.blocked else "sin-cupo")}
            for h, s in sorted(por_hora.items())]


# --- Operaciones del cliente -----------------------------------------------------------------------------------

def crear_cita(db: Session, user: CurrentUser, datos: dict[str, Any]) -> dict[str, Any]:
    """Crea la cita En Proceso y aparta franjas y repuestos en una sola transacción (RN-06, RN-08)."""
    cliente = _cliente(db, user.id)
    veh = db.scalar(select(Vehicle).where(Vehicle.id == datos["vehicle_id"], Vehicle.customer_id == cliente.id)
                    .with_for_update())  # serializa dos intentos sobre el mismo vehículo (RN-13)
    if veh is None:
        raise HTTPException(404, "Vehículo no encontrado")
    srv = _servicio(db, datos["service_id"])
    activa = db.scalar(select(Appointment).where(Appointment.vehicle_id == veh.id, Appointment.status.in_(ACTIVAS)))
    if activa:
        raise HTTPException(409, f"Este vehículo ya tiene una cita vigente: {activa.code} el "
                                 f"{activa.starts_at:%d/%m/%Y} a las {_hora12(activa.starts_at.hour)}.")
    fecha, h, n, now = datos["fecha"], int(datos["hora"][:2]), _n_franjas(srv), ahora()
    slots = _bloquear_franjas(db, [], fecha, list(range(h, h + n)))
    inicio = datetime.combine(fecha, time(h))
    if len(slots) != n or not all(_libre(s) for s in slots) or inicio <= now:
        raise HTTPException(409, _sugerencia(db, n, fecha, h))
    vence = now + timedelta(minutes=config.HOLD_MINUTES)
    a = Appointment(code=uuid.uuid4().hex[:20], customer_id=cliente.id, vehicle_id=veh.id, service_id=srv.id,
                    status="HELD", starts_at=inicio, hold_expires_at=vence)
    db.add(a)
    db.flush()
    a.code = f"CITA-{fecha:%Y%m%d}-{a.id:04d}"  # RN-14: el id garantiza unicidad sin otra secuencia
    for s in slots:
        s.booked_count += 1
        db.add(AppointmentSlot(appointment_id=a.id, slot_id=s.id))
    inventario.reservar_para_cita(db, srv.id, a.id, vence, veh.nominal_voltage_v,
                                  (datos.get("motivo_voltaje") or "").strip() or None, user.id)
    registrar(db, "appointments", "HELD", user.id, a.id, {"code": a.code, "starts_at": inicio.isoformat()})
    db.commit()
    return cita_out(db, a)


def confirmar(db: Session, user: CurrentUser, appointment_id: int) -> dict[str, Any]:
    a = _mi_cita(db, user, appointment_id)
    if a.status in VIGENTES:
        return cita_out(db, a)
    if a.status == "EXPIRED":
        raise HTTPException(410, EXPIRO)
    if a.status != "HELD":
        raise HTTPException(409, NO_VIGENTE)
    if a.hold_expires_at is None or a.hold_expires_at <= ahora():
        _liberar_cita(db, a, "EXPIRED", user.id)
        db.commit()
        raise HTTPException(410, EXPIRO)
    a.status, a.hold_expires_at = "CONFIRMED", None
    inventario.extender(db, a.id, a.starts_at + timedelta(minutes=config.NO_SHOW_MINUTES))  # RN-12
    registrar(db, "appointments", "CONFIRMED", user.id, a.id, {"from": "HELD"})
    db.commit()
    return cita_out(db, a)


def cancelar(db: Session, user: CurrentUser, appointment_id: int) -> dict[str, Any]:
    a = _mi_cita(db, user, appointment_id)
    if a.status not in ACTIVAS:
        raise HTTPException(409, NO_VIGENTE)
    if a.status != "HELD":  # abandonar el asistente no tiene ventana (RN-19)
        _ventana(a)
    _liberar_cita(db, a, "CANCELLED", user.id)
    db.commit()
    return cita_out(db, a)


def reprogramar(db: Session, user: CurrentUser, appointment_id: int, datos: dict[str, Any]) -> dict[str, Any]:
    """Toma las franjas nuevas y suelta las originales en una transacción; las reservas se conservan (RN-11)."""
    a = _mi_cita(db, user, appointment_id)
    if a.status not in VIGENTES:
        raise HTTPException(409, NO_VIGENTE)
    _ventana(a)
    fecha, h = datos["fecha"], int(datos["hora"][:2])
    inicio, n = datetime.combine(fecha, time(h)), _n_franjas(db.get(Service, a.service_id))  # type: ignore[arg-type]
    if inicio == a.starts_at:
        raise HTTPException(409, "Elige una hora distinta a la de tu cita.")
    viejas = _ids_franjas(db, a.id)
    bloqueadas = _bloquear_franjas(db, viejas, fecha, list(range(h, h + n)))
    for s in bloqueadas:
        if s.id in viejas:
            s.booked_count -= 1
    nuevas = [s for s in bloqueadas if s.slot_date == fecha and h <= s.start_time.hour < h + n]
    if len(nuevas) != n or not all(_libre(s) for s in nuevas) or inicio <= ahora():
        db.rollback()  # la cita conserva su horario
        raise HTTPException(409, _sugerencia(db, n, fecha, h))
    for s in nuevas:
        s.booked_count += 1
    for link in db.scalars(select(AppointmentSlot).where(AppointmentSlot.appointment_id == a.id)):
        db.delete(link)
    db.flush()
    for s in nuevas:
        db.add(AppointmentSlot(appointment_id=a.id, slot_id=s.id))
    registrar(db, "appointments", "RESCHEDULED", user.id, a.id,
              {"from": a.starts_at.isoformat(), "to": inicio.isoformat()})
    a.starts_at, a.status = inicio, "RESCHEDULED"
    inventario.extender(db, a.id, inicio + timedelta(minutes=config.NO_SHOW_MINUTES))
    db.commit()
    return cita_out(db, a)


def mis_citas(db: Session, user: CurrentUser) -> list[dict[str, Any]]:
    cliente = _cliente(db, user.id)
    return [cita_out(db, a) for a in db.scalars(select(Appointment).where(
        Appointment.customer_id == cliente.id, Appointment.status.in_(VIGENTES)).order_by(Appointment.starts_at))]


# --- Recepción: capacidad y bloqueos (HU-02) -------------------------------------------------------------------

def _franja_recepcion(db: Session, s: Slot) -> dict[str, Any]:
    pct = s.booked_count / s.capacity if s.capacity else 1
    semaforo, etiqueta = (("rojo", "Bloqueado") if s.blocked else ("rojo", "Sin cupo") if pct >= 1
                          else ("amarillo", "Pocos cupos") if pct >= 0.5 else ("verde", "Disponible"))  # RN-05
    citas = db.execute(select(Appointment, Customer.full_name, Vehicle.serial_number, Service.name)
                       .join(AppointmentSlot, AppointmentSlot.appointment_id == Appointment.id)
                       .join(Customer, Customer.id == Appointment.customer_id)
                       .join(Vehicle, Vehicle.id == Appointment.vehicle_id)
                       .join(Service, Service.id == Appointment.service_id)
                       .where(AppointmentSlot.slot_id == s.id, Appointment.status.in_(ACTIVAS))).all()
    return {"id": s.id, "fecha": s.slot_date, "hora": f"{s.start_time.hour:02d}:00", "capacidad": s.capacity,
            "ocupados": s.booked_count, "bloqueada": s.blocked, "motivo": s.block_reason, "semaforo": semaforo,
            "etiqueta": etiqueta,
            "citas": [{"id": a.id, "code": a.code, "status": a.status, "cliente": cli, "vehiculo": serie,
                       "servicio": srv} for a, cli, serie, srv in citas]}


def calendario(db: Session, fecha: date) -> dict[str, Any]:
    slots = db.scalars(select(Slot).where(Slot.slot_date == fecha).order_by(Slot.start_time))
    recordatorios = db.execute(select(Notification, Appointment.code, Appointment.starts_at)
                               .join(Appointment, Appointment.id == Notification.appointment_id)
                               .order_by(Notification.id.desc()).limit(20)).all()
    return {"fecha": fecha, "franjas": [_franja_recepcion(db, s) for s in slots],
            "recordatorios": [{"id": n.id, "code": code, "starts_at": inicio, "kind": n.kind, "status": n.status,
                               "sent_at": n.sent_at} for n, code, inicio in recordatorios]}


def bloqueo(db: Session, user: CurrentUser, slot_id: int, datos: dict[str, Any]) -> dict[str, Any]:
    """Bloquear no cancela las citas existentes: se listan para gestión manual (RN-04)."""
    motivo = (datos.get("motivo") or "").strip()
    if datos["bloquear"] and not motivo:
        raise HTTPException(422, "Indique el motivo del bloqueo")
    s = db.scalar(select(Slot).where(Slot.id == slot_id).with_for_update())
    if s is None:
        raise HTTPException(404, "Franja no encontrada")
    s.blocked, s.block_reason = datos["bloquear"], motivo if datos["bloquear"] else None
    registrar(db, "slots", "BLOCK" if s.blocked else "UNBLOCK", user.id, s.id, {"motivo": motivo or None})
    db.commit()
    return _franja_recepcion(db, s)


# --- Tareas periódicas (HU-28, HU-12): idempotentes, con SKIP LOCKED -------------------------------------------

@registrar_tarea("expirar_citas")
def expirar_citas(db: Session) -> None:
    for a in db.scalars(select(Appointment).where(Appointment.status == "HELD", Appointment.hold_expires_at <= ahora())
                        .order_by(Appointment.id).with_for_update(skip_locked=True)):
        _liberar_cita(db, a, "EXPIRED")


@registrar_tarea("marcar_inasistencias")
def marcar_inasistencias(db: Session) -> None:
    limite = ahora() - timedelta(minutes=config.NO_SHOW_MINUTES)
    sin_orden = ~exists(select(WorkOrder.id).where(WorkOrder.appointment_id == Appointment.id))
    for a in db.scalars(select(Appointment).where(Appointment.status.in_(VIGENTES), Appointment.starts_at < limite,
                                                  sin_orden).order_by(Appointment.id).with_for_update(skip_locked=True)):
        _liberar_cita(db, a, "NO_SHOW")


@registrar_tarea("generar_franjas")
def generar_franjas(db: Session) -> None:
    hoy = ahora().date()
    fin = hoy + timedelta(days=DIAS_GENERADOS)
    existentes = set(db.execute(select(Slot.slot_date, Slot.start_time).where(Slot.slot_date.between(hoy, fin))).all())
    for i in range(DIAS_GENERADOS + 1):
        d = hoy + timedelta(days=i)
        if d.weekday() == 6:  # RN-01: lunes a sábado
            continue
        for h in range(config.OPEN_HOUR, config.LAST_SLOT_HOUR + 1):
            if (d, time(h)) not in existentes:
                db.add(Slot(slot_date=d, start_time=time(h), capacity=CAPACIDAD, booked_count=0, blocked=False))


@registrar_tarea("recordatorios")
def recordatorios(db: Session) -> None:
    """Recordatorio de las citas de las próximas 24 h sin aviso; el envío se simula (ADR-15)."""
    now = ahora()
    ya_avisada = exists(select(Notification.id).where(Notification.appointment_id == Appointment.id,
                                                      Notification.kind == "REMINDER_24H"))
    for a in db.scalars(select(Appointment).where(
            Appointment.status.in_(VIGENTES), Appointment.starts_at > now,
            Appointment.starts_at <= now + timedelta(hours=24), ~ya_avisada)
            .order_by(Appointment.id).with_for_update(skip_locked=True)):
        n = Notification(appointment_id=a.id, kind="REMINDER_24H", status="PENDING", attempts=0)
        db.add(n)
        log.info("Recordatorio simulado para la cita %s del %s", a.code, a.starts_at)
        n.status, n.attempts, n.sent_at = "SENT", 1, now
