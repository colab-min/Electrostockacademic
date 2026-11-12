from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Appointment,
    AuditLog,
    Customer,
    Notification,
    Part,
    Service,
    ServicePart,
    Slot,
    Vehicle,
    WorkOrder,
)
from app.security import hash_tracking_code
from app.scheduling import allocate_queued_work_orders, release_work_order_slots
from app import tasks

BUSINESS_TIMEZONE = ZoneInfo("America/Bogota")


@pytest.fixture
def test_sessions(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(tasks, "SessionLocal", sessions)
    yield sessions
    engine.dispose()


def test_future_slots_cover_30_days_and_are_idempotent(test_sessions) -> None:
    start = date(2026, 11, 11)
    with test_sessions() as db:
        db.add(
            Slot(
                slot_date=start,
                start_time="08:00",
                capacity=2,
                booked_count=1,
            )
        )
        db.commit()

    tasks.add_future_slots(start)
    tasks.add_future_slots(start)

    with test_sessions() as db:
        slots = list(db.scalars(select(Slot).order_by(Slot.slot_date, Slot.start_time)))
        assert len(slots) == 260
        assert all(slot.slot_date.weekday() != 6 for slot in slots)
        assert all(slot.capacity == 3 for slot in slots)
        assert {slot.start_time for slot in slots} == {
            f"{hour:02d}:00" for hour in range(8, 18)
        }
        existing = next(
            slot
            for slot in slots
            if slot.slot_date == start and slot.start_time == "08:00"
        )
        assert existing.booked_count == 1


def test_expired_holds_release_reserved_parts_and_slots_once(test_sessions) -> None:
    now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    with test_sessions() as db:
        customer = Customer(
            full_name="Cliente de reserva",
            document_type="CC",
            document_number="1000000098",
            phone="3005550198",
            email="reserva@example.test",
        )
        db.add(customer)
        db.flush()
        vehicle = Vehicle(
            customer_id=customer.id,
            serial_number="SC-48-HOLD-01",
            brand="Electro",
            model="Ciudad",
        )
        service = Service(
            code="HOLD-SERVICE",
            name="Servicio de reserva",
            price=Decimal("10000"),
            duration_minutes=60,
        )
        part = Part(
            sku="HOLD-PART",
            name="Repuesto de reserva",
            unit_price=Decimal("5000"),
            physical_stock=2,
            reserved_stock=1,
        )
        slot = Slot(
            slot_date=date(2026, 11, 13),
            start_time="08:00",
            capacity=3,
            booked_count=1,
        )
        db.add_all([vehicle, service, part, slot])
        db.flush()
        db.add(ServicePart(service_id=service.id, part_id=part.id, quantity=1))
        appointment = Appointment(
            code="CITA-HOLD-0001",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            service_id=service.id,
            slot_id=slot.id,
            status="HELD",
            expires_at=now - timedelta(minutes=1),
        )
        db.add(appointment)
        db.commit()
        appointment_id = appointment.id
        slot_id = slot.id
        part_id = part.id

    assert tasks.expire_held_appointments(now) == 1
    assert tasks.expire_held_appointments(now) == 0
    with test_sessions() as db:
        assert db.get(Appointment, appointment_id).status == "EXPIRED"
        assert db.get(Slot, slot_id).booked_count == 0
        assert db.get(Part, part_id).reserved_stock == 0


def test_due_reminders_are_idempotent_and_mark_missing_contacts(test_sessions) -> None:
    now = datetime(2026, 11, 11, 8, tzinfo=BUSINESS_TIMEZONE)
    scheduled_date = now.date() + timedelta(days=1)
    with test_sessions() as db:
        customers = [
            Customer(
                full_name="Cliente con correo",
                document_type="CC",
                document_number="1000000097",
                phone="3005550197",
                email="recordatorio@example.test",
            ),
            Customer(
                full_name="Cliente sin correo",
                document_type="CC",
                document_number="1000000096",
                phone="3005550196",
                email=None,
            ),
        ]
        db.add_all(customers)
        db.flush()
        vehicle = Vehicle(
            customer_id=customers[0].id,
            serial_number="SC-48-REMINDER-01",
            brand="Electro",
            model="Ciudad",
        )
        service = Service(
            code="REMINDER-SERVICE",
            name="Servicio de recordatorio",
            price=Decimal("10000"),
            duration_minutes=60,
        )
        slots = [
            Slot(
                slot_date=scheduled_date,
                start_time=f"08:0{index}",
                capacity=3,
                booked_count=1,
            )
            for index in (5, 6)
        ]
        db.add_all([vehicle, service, *slots])
        db.flush()
        appointments = [
            Appointment(
                code=f"CITA-REMINDER-000{index}",
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                service_id=service.id,
                slot_id=slot.id,
                status="CONFIRMED",
            )
            for index, (customer, slot) in enumerate(zip(customers, slots), start=1)
        ]
        db.add_all(appointments)
        db.commit()
        appointment_ids = [appointment.id for appointment in appointments]

    assert tasks.send_due_reminders(now) == 2
    assert tasks.send_due_reminders(now) == 0
    with test_sessions() as db:
        notifications = list(db.scalars(select(Notification).order_by(Notification.appointment_id)))
        assert len(notifications) == 2
        assert {notification.status for notification in notifications} == {
            "SENT",
            "UNDELIVERED",
        }
        assert {notification.appointment_id for notification in notifications} == set(appointment_ids)


def test_walk_in_queue_prioritizes_fault_then_duration_and_reallocates(test_sessions) -> None:
    current_date = date(2026, 11, 11)
    scheduled_date = current_date + timedelta(days=1)
    with test_sessions() as db:
        customer = Customer(
            full_name="Cliente de cola",
            document_type="CC",
            document_number="1000000099",
            phone="3005550199",
            email="cola@example.test",
        )
        db.add(customer)
        db.flush()
        vehicle = Vehicle(
            customer_id=customer.id,
            serial_number="SC-48-QUEUE-01",
            brand="Electro",
            model="Ciudad",
        )
        db.add(vehicle)
        db.flush()
        for offset in range(30):
            slot_date = current_date + timedelta(days=offset)
            if slot_date.weekday() == 6:
                continue
            for hour in range(8, 18):
                available = slot_date == scheduled_date and hour == 8
                db.add(
                    Slot(
                        slot_date=slot_date,
                        start_time=f"{hour:02d}:00",
                        capacity=1,
                        booked_count=0,
                        blocked_reason=None if available else "Unavailable",
                    )
                )
        orders = [
            WorkOrder(
                number=f"OT-QUEUE-{index:02d}",
                tracking_code_hash=hash_tracking_code(f"QUEUE0000{index}"),
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                status="RECEIVED",
                queue_position=index,
                fault_priority=priority,
                estimated_duration_minutes=duration,
                created_at=datetime(2026, 11, 10, tzinfo=timezone.utc)
                + timedelta(minutes=index),
            )
            for index, (priority, duration) in enumerate(
                (
                    ("LOW", 30),
                    ("HIGH", 60),
                    ("HIGH", 30),
                    ("MEDIUM", 30),
                ),
                start=1,
            )
        ]
        db.add_all(orders)
        db.flush()

        assert allocate_queued_work_orders(
            db,
            datetime(2026, 11, 11, 8, tzinfo=BUSINESS_TIMEZONE),
        ) == 1
        assert orders[2].scheduled_start_at == datetime(
            2026,
            11,
            12,
            8,
            tzinfo=BUSINESS_TIMEZONE,
        )
        assert [orders[index].queue_position for index in (1, 3, 0)] == [1, 2, 3]

        orders[2].status = "ASSIGNED"
        release_work_order_slots(db, orders[2])
        assert allocate_queued_work_orders(
            db,
            datetime(2026, 11, 11, 8, tzinfo=BUSINESS_TIMEZONE),
        ) == 1
        assert orders[1].scheduled_start_at == datetime(
            2026,
            11,
            12,
            8,
            tzinfo=BUSINESS_TIMEZONE,
        )


def test_no_show_releases_slot_and_parts_once_and_keeps_attended_appointments(
    test_sessions,
) -> None:
    scheduled_date = date(2026, 11, 11)
    with test_sessions() as db:
        customer = Customer(
            full_name="Cliente de prueba",
            document_type="CC",
            document_number="1000000001",
            phone="3005550101",
            email="cliente@example.test",
        )
        db.add(customer)
        db.flush()
        vehicle = Vehicle(
            customer_id=customer.id,
            serial_number="SC-48-TASK-01",
            brand="Electro",
            model="Ciudad",
        )
        service = Service(
            code="TASK-SERVICE",
            name="Servicio de prueba",
            price=Decimal("10000"),
            duration_minutes=60,
        )
        part = Part(
            sku="TASK-PART",
            name="Repuesto de prueba",
            unit_price=Decimal("5000"),
            physical_stock=10,
            reserved_stock=3,
        )
        db.add_all([vehicle, service, part])
        db.flush()
        db.add(ServicePart(service_id=service.id, part_id=part.id, quantity=1))
        slot = Slot(
            slot_date=scheduled_date,
            start_time="08:00",
            capacity=3,
            booked_count=2,
        )
        not_due_slot = Slot(
            slot_date=scheduled_date,
            start_time="08:01",
            capacity=3,
            booked_count=1,
        )
        db.add_all([slot, not_due_slot])
        db.flush()

        no_show = Appointment(
            code="CITA-TASK-0001",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            service_id=service.id,
            slot_id=slot.id,
            status="CONFIRMED",
        )
        not_due = Appointment(
            code="CITA-TASK-0002",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            service_id=service.id,
            slot_id=not_due_slot.id,
            status="CONFIRMED",
        )
        attended = Appointment(
            code="CITA-TASK-0003",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            service_id=service.id,
            slot_id=slot.id,
            status="CONFIRMED",
        )
        db.add_all([no_show, not_due, attended])
        db.flush()
        db.add(
            WorkOrder(
                number="OT-TASK-0001",
                tracking_code_hash=hash_tracking_code("TASK000001"),
                appointment_id=attended.id,
                customer_id=customer.id,
                vehicle_id=vehicle.id,
                status="RECEIVED",
            )
        )
        db.commit()
        no_show_id = no_show.id
        not_due_id = not_due.id
        attended_id = attended.id
        slot_id = slot.id
        not_due_slot_id = not_due_slot.id
        part_id = part.id

    before_grace_period = datetime.combine(
        scheduled_date,
        time(8, 14, 59),
        BUSINESS_TIMEZONE,
    )
    grace_period_elapsed = before_grace_period + timedelta(seconds=1)
    assert tasks.mark_no_show_appointments(before_grace_period) == 0
    assert tasks.mark_no_show_appointments(grace_period_elapsed) == 1
    assert tasks.mark_no_show_appointments(grace_period_elapsed) == 0

    with test_sessions() as db:
        assert db.get(Appointment, no_show_id).status == "NO_SHOW"
        assert db.get(Appointment, not_due_id).status == "CONFIRMED"
        assert db.get(Appointment, attended_id).status == "CONFIRMED"
        assert db.get(Slot, slot_id).booked_count == 1
        assert db.get(Slot, not_due_slot_id).booked_count == 1
        assert db.get(Part, part_id).reserved_stock == 2
        assert db.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "APPOINTMENT_NO_SHOW"
            )
        ) == 1
