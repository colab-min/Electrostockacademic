import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Appointment,
    AuditLog,
    Customer,
    InventoryMovement,
    Notification,
    Part,
    Slot,
    WorkOrder,
)
from app.scheduling import (
    allocate_queued_work_orders,
    get_appointment_parts,
    get_appointment_slots,
)

logger = logging.getLogger("electrostock.tasks")
BUSINESS_TIMEZONE = ZoneInfo("America/Bogota")


def expire_held_appointments(now: datetime | None = None) -> int:
    current_time = now or datetime.now(timezone.utc)
    expired_count = 0
    with SessionLocal() as db:
        appointments = db.scalars(
            select(Appointment)
            .where(
                Appointment.status == "HELD",
                Appointment.expires_at <= current_time,
            )
            .with_for_update()
        )
        for appointment in appointments:
            appointment_slots = get_appointment_slots(
                db,
                appointment,
                lock=True,
            )
            for part, quantity in get_appointment_parts(
                db,
                appointment,
                lock=True,
            ):
                part.reserved_stock = max(0, part.reserved_stock - quantity)
            for slot in appointment_slots:
                slot.booked_count = max(0, slot.booked_count - 1)
            appointment.status = "EXPIRED"
            db.add(
                AuditLog(
                    actor_id=None,
                    action="APPOINTMENT_EXPIRED",
                    entity="appointment",
                    entity_id=appointment.id,
                    details="La reserva de cinco minutos venció",
                )
            )
            expired_count += 1
        db.commit()
    if expired_count:
        logger.info("Expired %d appointment holds", expired_count)
    return expired_count


def send_due_reminders(now: datetime | None = None) -> int:
    current_time = now or datetime.now(timezone.utc)
    local_now = current_time.astimezone(BUSINESS_TIMEZONE)
    window_start = local_now + timedelta(hours=24)
    window_end = window_start + timedelta(minutes=15)
    reminder_count = 0
    with SessionLocal() as db:
        rows = db.execute(
            select(Appointment, Slot, Customer)
            .join(Slot, Appointment.slot_id == Slot.id)
            .join(Customer, Appointment.customer_id == Customer.id)
            .where(Appointment.status.in_(("CONFIRMED", "RESCHEDULED")))
        ).all()
        for appointment, slot, customer in rows:
            start = datetime.combine(
                slot.slot_date,
                time.fromisoformat(slot.start_time),
                BUSINESS_TIMEZONE,
            )
            if not window_start <= start < window_end:
                continue
            key = f"reminder:{appointment.id}"
            if db.scalar(
                select(Notification.id).where(Notification.idempotency_key == key)
            ):
                continue
            contact = customer.email or ""
            valid_contact = "@" in contact
            notification = Notification(
                appointment_id=appointment.id,
                kind="REMINDER_24H",
                recipient=contact,
                payload={"kind": "REMINDER_24H", "appointment_code": appointment.code},
                status="SENT" if valid_contact else "UNDELIVERED",
                attempts=1 if valid_contact else 0,
                idempotency_key=key,
            )
            db.add(notification)
            reminder_count += 1
            if valid_contact:
                logger.info("notification_sent kind=REMINDER_24H appointment=%s", appointment.code)
            else:
                logger.warning("notification_undelivered appointment=%s reason=no_contact", appointment.code)
        db.commit()
    return reminder_count


def mark_no_show_appointments(now: datetime | None = None) -> int:
    current_time = now or datetime.now(timezone.utc)
    local_now = current_time.astimezone(BUSINESS_TIMEZONE)
    no_show_count = 0
    with SessionLocal() as db:
        candidate_ids = db.scalars(
            select(Appointment.id)
            .join(Slot, Appointment.slot_id == Slot.id)
            .where(
                Appointment.status.in_(("CONFIRMED", "RESCHEDULED")),
                Slot.slot_date <= local_now.date(),
            )
            .order_by(Appointment.id)
        ).all()
        for appointment_id in candidate_ids:
            appointment = db.scalar(
                select(Appointment)
                .where(Appointment.id == appointment_id)
                .with_for_update(skip_locked=True)
            )
            if appointment is None or appointment.status not in {"CONFIRMED", "RESCHEDULED"}:
                continue
            appointment_slots = get_appointment_slots(
                db,
                appointment,
                lock=True,
            )
            slot = next(
                (
                    candidate
                    for candidate in appointment_slots
                    if candidate.id == appointment.slot_id
                ),
                None,
            )
            if slot is None:
                continue
            scheduled_start = datetime.combine(
                slot.slot_date,
                time.fromisoformat(slot.start_time),
                BUSINESS_TIMEZONE,
            )
            if local_now < scheduled_start + timedelta(minutes=15):
                continue
            if db.scalar(
                select(WorkOrder.id).where(
                    WorkOrder.appointment_id == appointment.id
                )
            ):
                continue

            for part, quantity in get_appointment_parts(
                db,
                appointment,
                lock=True,
            ):
                part.reserved_stock = max(0, part.reserved_stock - quantity)

            for appointment_slot in appointment_slots:
                appointment_slot.booked_count = max(
                    0,
                    appointment_slot.booked_count - 1,
                )
            appointment.status = "NO_SHOW"
            db.add(
                AuditLog(
                    actor_id=None,
                    action="APPOINTMENT_NO_SHOW",
                    entity="appointment",
                    entity_id=appointment.id,
                    details="La cita no tuvo una orden de trabajo 15 minutos después de su inicio",
                )
            )
            db.flush()
            no_show_count += 1
        db.commit()
    if no_show_count:
        logger.info("Marked %d appointments as no-show", no_show_count)
    return no_show_count


def add_future_slots(start: date, days: int = 30) -> None:
    with SessionLocal() as db:
        for offset in range(days):
            slot_date = start + timedelta(days=offset)
            if slot_date.weekday() == 6:
                continue
            for hour in range(8, 18):
                start_time = f"{hour:02d}:00"
                slot = db.scalar(
                    select(Slot)
                    .where(
                        Slot.slot_date == slot_date,
                        Slot.start_time == start_time,
                    )
                    .with_for_update()
                )
                if slot is None:
                    db.add(
                        Slot(
                            slot_date=slot_date,
                            start_time=start_time,
                            capacity=3,
                            booked_count=0,
                        )
                    )
                elif slot.capacity < 3:
                    slot.capacity = 3
        db.commit()


def allocate_pending_work_orders(now: datetime | None = None) -> int:
    with SessionLocal() as db:
        scheduled_count = allocate_queued_work_orders(db, now)
        db.commit()
    if scheduled_count:
        logger.info("Scheduled %d queued work orders", scheduled_count)
    return scheduled_count


async def run_scheduler() -> None:
    generated_through_date = datetime.now(BUSINESS_TIMEZONE).date()
    await asyncio.to_thread(add_future_slots, generated_through_date, 30)
    await asyncio.to_thread(allocate_pending_work_orders)
    reminder_check = 0
    while True:
        local_today = datetime.now(BUSINESS_TIMEZONE).date()
        if local_today > generated_through_date:
            await asyncio.to_thread(add_future_slots, local_today, 30)
            generated_through_date = local_today
        await asyncio.to_thread(expire_held_appointments)
        await asyncio.to_thread(mark_no_show_appointments)
        await asyncio.to_thread(allocate_pending_work_orders)
        if reminder_check == 0:
            await asyncio.to_thread(send_due_reminders)
        reminder_check = (reminder_check + 1) % 15
        await asyncio.sleep(60)
