from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentPartReservation,
    AppointmentSlot,
    Part,
    ServicePart,
    Slot,
    WorkOrder,
    WorkOrderSlot,
)

BUSINESS_TIMEZONE = ZoneInfo("America/Bogota")


def required_slot_count(duration_minutes: int) -> int:
    return max(1, (duration_minutes + 59) // 60)


def slot_start_datetime(slot: Slot) -> datetime:
    return datetime.combine(
        slot.slot_date,
        time.fromisoformat(slot.start_time),
        BUSINESS_TIMEZONE,
    )


def required_slot_starts(start_slot: Slot, duration_minutes: int) -> list[datetime]:
    start = datetime.combine(
        start_slot.slot_date,
        time.fromisoformat(start_slot.start_time),
    )
    return [
        start + timedelta(hours=offset)
        for offset in range(required_slot_count(duration_minutes))
    ]


def slots_from_start_map(
    start_slot: Slot,
    duration_minutes: int,
    slots_by_start: dict[tuple[date, str], Slot],
) -> list[Slot]:
    expected_starts = required_slot_starts(start_slot, duration_minutes)
    if any(slot_start.date() != start_slot.slot_date for slot_start in expected_starts):
        return []
    return [
        slots_by_start[(slot_start.date(), slot_start.strftime("%H:%M"))]
        for slot_start in expected_starts
        if (slot_start.date(), slot_start.strftime("%H:%M")) in slots_by_start
    ]


def get_required_slots(
    db: Session,
    start_slot: Slot,
    duration_minutes: int,
    *,
    lock: bool = False,
) -> list[Slot]:
    expected_starts = required_slot_starts(start_slot, duration_minutes)
    if any(slot_start.date() != start_slot.slot_date for slot_start in expected_starts):
        return []

    statement = select(Slot).where(
        or_(
            *(
                and_(
                    Slot.slot_date == slot_start.date(),
                    Slot.start_time == slot_start.strftime("%H:%M"),
                )
                for slot_start in expected_starts
            )
        )
    )
    if lock:
        statement = (
            statement.order_by(Slot.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    slots_by_start = {
        (slot.slot_date, slot.start_time): slot
        for slot in db.scalars(statement)
    }
    return slots_from_start_map(start_slot, duration_minutes, slots_by_start)


def get_appointment_slots(
    db: Session,
    appointment: Appointment,
    *,
    lock: bool = False,
) -> list[Slot]:
    slot_ids = list(
        db.scalars(
            select(AppointmentSlot.slot_id).where(
                AppointmentSlot.appointment_id == appointment.id
            )
        )
    )
    if not slot_ids:
        slot_ids = [appointment.slot_id]

    statement = select(Slot).where(Slot.id.in_(slot_ids)).order_by(Slot.id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return list(db.scalars(statement))


def lock_slots(db: Session, slot_ids: set[str]) -> list[Slot]:
    if not slot_ids:
        return []
    return list(
        db.scalars(
            select(Slot)
            .where(Slot.id.in_(slot_ids))
            .order_by(Slot.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )


def get_appointment_parts(
    db: Session,
    appointment: Appointment,
    *,
    lock: bool = False,
) -> list[tuple[Part, int]]:
    statement = (
        select(Part, AppointmentPartReservation.quantity)
        .join(
            AppointmentPartReservation,
            AppointmentPartReservation.part_id == Part.id,
        )
        .where(
            AppointmentPartReservation.appointment_id == appointment.id,
        )
        .order_by(Part.id)
    )
    if lock:
        statement = statement.with_for_update()
    rows = db.execute(statement).all()
    if rows:
        return [(part, quantity) for part, quantity in rows]

    statement = (
        select(Part, ServicePart.quantity)
        .join(ServicePart, ServicePart.part_id == Part.id)
        .where(ServicePart.service_id == appointment.service_id)
        .order_by(Part.id)
    )
    if lock:
        statement = statement.with_for_update()
    return [(part, quantity) for part, quantity in db.execute(statement).all()]


def add_appointment_slots(
    db: Session,
    appointment: Appointment,
    slots: list[Slot],
) -> None:
    db.add_all(
        AppointmentSlot(appointment_id=appointment.id, slot_id=slot.id)
        for slot in slots
    )


FAULT_TYPES = (
    {"code": "F01", "name": "Batería no carga", "priority": "HIGH"},
    {"code": "F02", "name": "Frenos sin respuesta", "priority": "HIGH"},
    {"code": "F03", "name": "Falla eléctrica", "priority": "MEDIUM"},
    {"code": "F04", "name": "Mantenimiento preventivo", "priority": "LOW"},
)
FAULT_PRIORITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _queue_sort_key(order: WorkOrder) -> tuple[int, int, datetime, str]:
    created_at = order.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return (
        FAULT_PRIORITY_RANK.get(order.fault_priority, FAULT_PRIORITY_RANK["MEDIUM"]),
        order.estimated_duration_minutes,
        created_at,
        order.id,
    )


def _ensure_slot_horizon(db: Session, start: date, days: int) -> None:
    for offset in range(days):
        slot_date = start + timedelta(days=offset)
        if slot_date.weekday() == 6:
            continue
        for hour in range(8, 18):
            start_time = f"{hour:02d}:00"
            existing = db.scalar(
                select(Slot).where(
                    Slot.slot_date == slot_date,
                    Slot.start_time == start_time,
                )
            )
            if existing is None:
                db.add(
                    Slot(
                        slot_date=slot_date,
                        start_time=start_time,
                        capacity=3,
                        booked_count=0,
                    )
                )


def _available_work_order_slots(
    db: Session,
    order: WorkOrder,
    current_time: datetime,
) -> list[Slot]:
    candidates = list(
        db.scalars(
            select(Slot)
            .where(Slot.slot_date >= current_time.date())
            .order_by(Slot.slot_date, Slot.start_time)
        )
    )
    for candidate in candidates:
        if slot_start_datetime(candidate) <= current_time:
            continue
        required = get_required_slots(
            db,
            candidate,
            order.estimated_duration_minutes,
            lock=True,
        )
        if len(required) != required_slot_count(order.estimated_duration_minutes):
            continue
        if any(
            slot.blocked_reason or slot.booked_count >= slot.capacity
            for slot in required
        ):
            continue
        return required
    return []


def allocate_queued_work_orders(
    db: Session,
    now: datetime | None = None,
) -> int:
    current_time = (now or datetime.now(timezone.utc)).astimezone(BUSINESS_TIMEZONE)
    _ensure_slot_horizon(db, current_time.date(), 30)
    db.flush()
    queue = list(
        db.scalars(
            select(WorkOrder)
            .where(
                WorkOrder.status == "RECEIVED",
                WorkOrder.queue_position.is_not(None),
            )
            .with_for_update()
        )
    )
    queue.sort(key=_queue_sort_key)
    scheduled_count = 0
    for order in queue:
        slots = _available_work_order_slots(db, order, current_time)
        if not slots:
            continue
        for slot in slots:
            slot.booked_count += 1
            db.add(WorkOrderSlot(work_order_id=order.id, slot_id=slot.id))
        order.scheduled_start_at = slot_start_datetime(slots[0])
        order.queue_position = None
        scheduled_count += 1
        db.flush()

    waiting = [order for order in queue if order.queue_position is not None]
    waiting.sort(key=_queue_sort_key)
    for position, order in enumerate(waiting, start=1):
        order.queue_position = position
    return scheduled_count


def release_work_order_slots(
    db: Session,
    order: WorkOrder,
    *,
    lock: bool = False,
) -> None:
    slot_ids = list(
        db.scalars(
            select(WorkOrderSlot.slot_id).where(
                WorkOrderSlot.work_order_id == order.id
            )
        )
    )
    slots = list(
        db.scalars(
            select(Slot)
            .where(Slot.id.in_(slot_ids))
            .order_by(Slot.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ) if slot_ids else []
    for slot in slots:
        slot.booked_count = max(0, slot.booked_count - 1)
    db.query(WorkOrderSlot).filter(
        WorkOrderSlot.work_order_id == order.id
    ).delete(synchronize_session=False)
    order.scheduled_start_at = None
