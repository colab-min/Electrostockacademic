"""Carga fixtures/seed.json en MySQL al arrancar (si la base está vacía o con RESET_SEED=true)."""

import hashlib
import json
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app import config
from app.db import Base, SessionLocal, engine
from app.modulos.agenda.modelos import Appointment, AppointmentSlot, Slot
from app.modulos.auditoria import modelos as _auditoria  # noqa: F401  (registra audit_log en el esquema)
from app.modulos.catalogo.modelos import FaultType, Service, ServicePart
from app.modulos.clientes.modelos import Customer, TechnicalNote, Vehicle
from app.modulos.facturacion.modelos import Payment, Receipt, Survey
from app.modulos.identidad.modelos import User
from app.modulos.inventario.modelos import Part, PartReservation
from app.modulos.ordenes.modelos import (Sequence, WorkOrder, WorkOrderPart, WorkOrderService, WorkOrderSlot,
                                         WorkOrderStatusHistory)
from app.seguridad import hash_password

ACTIVE_APPOINTMENT = {"HELD", "CONFIRMED", "RESCHEDULED"}


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def now_local() -> datetime:
    """Hora local del taller, sin zona (la base guarda hora local en esta demo)."""
    return datetime.now(config.TZ).replace(tzinfo=None, microsecond=0)


def business_day(base: date, offset: int) -> date:
    d = base + timedelta(days=offset)
    return d + timedelta(days=1) if d.weekday() == 6 else d


def create_schema() -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        triggers = {r[0] for r in conn.execute(text("SHOW TRIGGERS LIKE 'audit_log'"))}
        for event in ("UPDATE", "DELETE"):
            name = f"audit_log_no_{event.lower()}"
            if name not in triggers:
                conn.execute(text(f"CREATE TRIGGER {name} BEFORE {event} ON audit_log FOR EACH ROW "
                                  "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_log es append-only'"))


def reset_data() -> None:
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in inspect(engine).get_table_names():
            conn.execute(text(f"TRUNCATE TABLE `{table}`"))  # TRUNCATE no dispara los triggers
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def load(db: Session, data: dict[str, Any], now: datetime) -> None:
    today = business_day(now.date(), 0)
    ids: dict[str, int] = {}

    def at(spec: dict[str, Any] | None) -> datetime | None:
        if spec is None:
            return None
        h, m = map(int, spec["time"].split(":"))
        return datetime.combine(business_day(today, spec["day"]), time(h, m))

    def add(alias: str, obj: Any) -> Any:
        db.add(obj)
        db.flush()
        ids[alias] = obj.id
        return obj

    for u in data["users"]:
        add(u["id"], User(full_name=u["full_name"], email=u["email"], password_hash=hash_password(u["password"]),
                          role=u["role"], active=u["active"], must_change_password=u["must_change_password"]))
    for c in data["customers"]:
        add(c["id"], Customer(user_id=ids.get(c["user"]) if c["user"] else None, document_type=c["document_type"],
                              document_number=c["document_number"], full_name=c["full_name"], phone=c["phone"],
                              email=c["email"], data_consent_at=now, data_consent_version=c["data_consent_version"]))
    for v in data["vehicles"]:
        fields = {k: v[k] for k in v if k not in ("id", "customer")}
        add(v["id"], Vehicle(customer_id=ids[v["customer"]], **fields))
    for p in data["parts"]:
        add(p["id"], Part(**{k: p[k] for k in p if k != "id"}))
    for s in data["services"]:
        add(s["id"], Service(**{k: s[k] for k in s if k != "id"}))
    for sp in data["service_parts"]:
        db.add(ServicePart(service_id=ids[sp["service"]], part_id=ids[sp["part"]], quantity=sp["quantity"]))
    for f in data["fault_types"]:
        add(f["id"], FaultType(**{k: f[k] for k in f if k != "id"}))

    # Franjas: hoy + 30 días, lunes a sábado, 08:00 a 17:00, más las pasadas que usan citas y órdenes.
    settings = data["settings"]
    slots: dict[tuple[date, time], Slot] = {}

    def slot(d: date, t: time) -> Slot:
        if (d, t) not in slots:
            slots[(d, t)] = Slot(slot_date=d, start_time=t, capacity=settings["capacity"], booked_count=0)
            db.add(slots[(d, t)])
        return slots[(d, t)]

    for offset in range(settings["generate_days"] + 1):
        d = today + timedelta(days=offset)
        if d.weekday() != 6:
            for h in range(config.OPEN_HOUR, config.LAST_SLOT_HOUR + 1):
                slot(d, time(h))
    for b in settings["blocked"]:
        s = slot(*divmod_spec(at(b)))
        s.blocked, s.block_reason = True, b["reason"]

    services = {s["id"]: s for s in data["services"]}
    used_today = {at(spec).time() for o in data["work_orders"] for spec in o["slots"]  # type: ignore[union-attr]
                  if at(spec).date() == today}  # type: ignore[union-attr]
    used_today |= {at(a["start"]).time() for a in data["appointments"]  # type: ignore[union-attr]
                   if a["start"]["time"] != "next" and at(a["start"]).date() == today}  # type: ignore[union-attr]
    next_hour = next((h for h in range(config.OPEN_HOUR, config.LAST_SLOT_HOUR + 1)
                      if datetime.combine(today, time(h)) > now and time(h) not in used_today), config.LAST_SLOT_HOUR)

    db.flush()
    for a in data["appointments"]:
        start = dict(a["start"])
        if start["time"] == "next":
            start["time"] = f"{next_hour:02d}:00"
        starts_at = at(start)
        assert starts_at
        hold = now + timedelta(minutes=a["hold_expires_minutes"]) if a["status"] == "HELD" else None
        prefix, _, seq = a["code"].split("-")
        appt = add(a["id"], Appointment(code=f"{prefix}-{starts_at:%Y%m%d}-{seq}", customer_id=ids[a["customer"]],
                                        vehicle_id=ids[a["vehicle"]], service_id=ids[a["service"]],
                                        status=a["status"], starts_at=starts_at, hold_expires_at=hold))
        for i in range(-(-services[a["service"]]["duration_min"] // 60)):
            s = slot(starts_at.date(), time(starts_at.hour + i))
            db.flush()
            db.add(AppointmentSlot(appointment_id=appt.id, slot_id=s.id))
            if a["status"] in ACTIVE_APPOINTMENT:
                s.booked_count += 1
    appt_start = {a.code: a for a in db.scalars(select(Appointment))}

    prices = {p["id"]: p["sale_price"] for p in data["parts"]}
    for o in data["work_orders"]:
        wo = add(o["id"], WorkOrder(
            number=o["number"], tracking_code_hash=sha256(o["tracking_code"]), vehicle_id=ids[o["vehicle"]],
            appointment_id=ids.get(o["appointment"]) if o["appointment"] else None, origin=o["origin"],
            fault_type_id=ids.get(o["fault_type"]) if o["fault_type"] else None, priority=o["priority"],
            mechanic_id=ids.get(o["mechanic"]) if o["mechanic"] else None, status=o["status"],
            intake_reason=o["intake_reason"], diagnosis=o["diagnosis"], queue_position=o["queue_position"],
            estimated_delivery_at=at(o["estimated_delivery_at"]), created_at=at(o["history"][0]["at"])))
        for sid in o["services"]:
            db.add(WorkOrderService(work_order_id=wo.id, service_id=ids[sid], applied_price=services[sid]["labor_price"]))
        for spec in o["slots"]:
            when = at(spec)
            assert when
            s = slot(when.date(), when.time())
            db.flush()
            db.add(WorkOrderSlot(work_order_id=wo.id, slot_id=s.id))
            if o["status"] != "CANCELLED":
                s.booked_count += 1
        for h in o["history"]:
            db.add(WorkOrderStatusHistory(work_order_id=wo.id, from_status=h["from"], to_status=h["to"],
                                          user_id=ids[h["user"]], created_at=at(h["at"])))
    for r in data["reservations"]:
        appt_id = ids[r["appointment"]] if r["appointment"] else None
        expires = None
        if r["work_order"] is None and appt_id:
            appt = next(a for a in appt_start.values() if a.id == appt_id)
            expires = appt.starts_at + timedelta(minutes=config.NO_SHOW_MINUTES)
        add(r["id"], PartReservation(part_id=ids[r["part"]], appointment_id=appt_id,
                                     work_order_id=ids.get(r["work_order"]) if r["work_order"] else None,
                                     quantity=r["quantity"], status=r["status"], expires_at=expires))
    for o in data["work_orders"]:
        for line in o["parts"]:
            db.add(WorkOrderPart(work_order_id=ids[o["id"]], part_id=ids[line["part"]],
                                 reservation_id=ids.get(line["reservation"]) if line["reservation"] else None,
                                 quantity=line["quantity"], unit_price=prices[line["part"]], status=line["status"]))
    for n in data["technical_notes"]:
        db.add(TechnicalNote(vehicle_id=ids[n["vehicle"]], work_order_id=ids[n["work_order"]],
                             author_id=ids[n["author"]], content_html=n["content_html"], created_at=at(n["at"])))
    for r in data["receipts"]:
        db.add(Receipt(work_order_id=ids[r["work_order"]], number=r["number"], subtotal=r["subtotal"], vat=r["vat"],
                       total=r["total"], created_at=at(r["at"])))
    for p in data["payments"]:
        db.add(Payment(work_order_id=ids[p["work_order"]], amount=p["amount"], method=p["method"],
                       created_at=at(p["at"])))
    for s in data["surveys"]:
        db.add(Survey(work_order_id=ids[s["work_order"]], token=s["token"], score=s["score"], comment=s["comment"],
                      answered_at=at(s["at"])))
    for name, value in data["sequences"].items():
        db.add(Sequence(name=name, value=value))


def divmod_spec(when: datetime | None) -> tuple[date, time]:
    assert when
    return when.date(), when.time()


def seed_if_needed() -> bool:
    create_schema()
    with SessionLocal() as db:
        empty = db.scalar(select(User.id).limit(1)) is None
    if not (empty or config.RESET_SEED):
        return False
    reset_data()
    with open(config.SEED_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    with SessionLocal() as db:
        load(db, data, now_local())
        db.commit()
    return True


if __name__ == "__main__":
    config.RESET_SEED = True
    print("Semilla cargada" if seed_if_needed() else "Sin cambios")
