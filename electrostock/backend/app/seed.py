import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Appointment,
    AppointmentPartReservation,
    Customer,
    Part,
    Payment,
    Service,
    ServicePart,
    Slot,
    TechnicalNote,
    User,
    Vehicle,
    WorkOrder,
    WorkOrderPart,
    WorkOrderService,
)
from app.security import hash_password, hash_tracking_code
from app.scheduling import add_appointment_slots, get_appointment_parts
from app.sequences import synchronize_sequence


def seed_database(db: Session, fixture_path: Path) -> None:
    if not fixture_path.exists():
        return
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    users: dict[str, User] = {}
    for row in data.get("users", []):
        email = row["email"].lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                full_name=row["full_name"],
                email=email,
                password_hash=hash_password(row["password"]),
                role=row["role"],
                active=row.get("active", True),
                must_change_password=row.get("must_change_password", False),
            )
            db.add(user)
            db.flush()
        users[row["key"]] = user

    customers: dict[str, Customer] = {}
    for row in data.get("customers", []):
        customer = db.scalar(
            select(Customer).where(
                Customer.document_type == row["document_type"],
                Customer.document_number == row["document_number"],
            )
        )
        if customer is None:
            owner = users.get(row.get("user_key"))
            customer = Customer(
                user_id=owner.id if owner else None,
                full_name=row["full_name"],
                document_type=row["document_type"],
                document_number=row["document_number"],
                phone=row.get("phone", ""),
                email=row.get("email"),
                data_consent_version="v1",
            )
            db.add(customer)
            db.flush()
        customers[row["key"]] = customer

    vehicles: dict[str, Vehicle] = {}
    for row in data.get("vehicles", []):
        vehicle = db.scalar(
            select(Vehicle).where(Vehicle.serial_number == row["serial_number"])
        )
        if vehicle is None:
            vehicle = Vehicle(
                customer_id=customers[row["customer_key"]].id,
                serial_number=row["serial_number"],
                plate=row.get("plate"),
                brand=row["brand"],
                model=row["model"],
                year=row.get("year"),
                battery_capacity_ah=row.get("battery_capacity_ah"),
                cell_type=row.get("cell_type"),
                motor_power_w=row.get("motor_power_w"),
                controller=row.get("controller"),
            )
            db.add(vehicle)
            db.flush()
        vehicles[row["key"]] = vehicle

    parts: dict[str, Part] = {}
    for row in data.get("parts", []):
        part = db.scalar(select(Part).where(Part.sku == row["sku"]))
        if part is None:
            part = Part(
                sku=row["sku"],
                name=row["name"],
                category=row.get("category", "General"),
                voltage=row.get("voltage"),
                unit_price=row["unit_price"],
                physical_stock=row["physical_stock"],
                reserved_stock=0,
                min_threshold=row.get("min_threshold", 0),
            )
            db.add(part)
            db.flush()
        parts[row["key"]] = part

    services: dict[str, Service] = {}
    for row in data.get("services", []):
        service = db.scalar(select(Service).where(Service.code == row["code"]))
        if service is None:
            service = Service(
                code=row["code"],
                name=row["name"],
                description=row.get("description", ""),
                price=row["price"],
                duration_minutes=row["duration_minutes"],
            )
            db.add(service)
            db.flush()
        services[row["key"]] = service

    for row in data.get("service_parts", []):
        existing = db.scalar(
            select(ServicePart.id).where(
                ServicePart.service_id == services[row["service_key"]].id,
                ServicePart.part_id == parts[row["part_key"]].id,
            )
        )
        if existing is None:
            db.add(
                ServicePart(
                    service_id=services[row["service_key"]].id,
                    part_id=parts[row["part_key"]].id,
                    quantity=row["quantity"],
                )
            )

    for row in data.get("appointments", []):
        slot_date = date.today() + timedelta(days=row.get("day_offset", 1))
        if slot_date.weekday() == 6:
            slot_date += timedelta(days=1)
        slot = db.scalar(
            select(Slot).where(
                Slot.slot_date == slot_date,
                Slot.start_time == row["start_time"],
            )
        )
        if slot is None:
            slot = Slot(
                slot_date=slot_date,
                start_time=row["start_time"],
                capacity=row.get("capacity", 3),
                booked_count=0,
            )
            db.add(slot)
            db.flush()
        appointment = db.scalar(
            select(Appointment).where(Appointment.code == row["code"])
        )
        if appointment is None:
            now = datetime.now(timezone.utc)
            expires_at = None
            if row["status"] == "HELD":
                expires_at = now + timedelta(minutes=row.get("expires_in_minutes", 5))
            appointment = Appointment(
                code=row["code"],
                customer_id=customers[row["customer_key"]].id,
                vehicle_id=vehicles[row["vehicle_key"]].id,
                service_id=services[row["service_key"]].id,
                slot_id=slot.id,
                status=row["status"],
                expires_at=expires_at,
            )
            slot.booked_count += 1
            db.add(appointment)
            db.flush()
            add_appointment_slots(db, appointment, [slot])
            appointment_parts = get_appointment_parts(db, appointment)
            db.add_all(
                AppointmentPartReservation(
                    appointment_id=appointment.id,
                    part_id=part.id,
                    quantity=quantity,
                )
                for part, quantity in appointment_parts
            )
            if appointment.status in {"HELD", "CONFIRMED", "RESCHEDULED"}:
                for part, quantity in appointment_parts:
                    part.reserved_stock += quantity
    for row in data.get("work_orders", []):
        order = db.scalar(
            select(WorkOrder).where(WorkOrder.number == row["number"])
        )
        if order is not None:
            continue
        vehicle = vehicles[row["vehicle_key"]]
        customer = customers[row["customer_key"]]
        order = WorkOrder(
            number=row["number"],
            tracking_code_hash=hash_tracking_code(row["tracking_code"]),
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            mechanic_id=users[row["mechanic_key"]].id if row.get("mechanic_key") else None,
            status=row["status"],
            fault_description=row.get("fault_description", ""),
            diagnosis=row.get("diagnosis", ""),
            expected_part_date=(
                date.today() + timedelta(days=row["expected_part_day_offset"])
                if row.get("expected_part_day_offset") is not None
                else None
            ),
            expected_part_id=(
                parts[row["expected_part_key"]].id
                if row.get("expected_part_key")
                else None
            ),
            queue_position=row.get("queue_position"),
        )
        db.add(order)
        db.flush()
        if row.get("service_key"):
            service = services[row["service_key"]]
            db.add(
                WorkOrderService(
                    work_order_id=order.id,
                    service_name=service.name,
                    applied_price=service.price,
                )
            )
        for line in row.get("parts", []):
            part = parts[line["part_key"]]
            quantity = line["quantity"]
            status = line.get("status", "RESERVED")
            if status == "RESERVED":
                part.reserved_stock += quantity
            db.add(
                WorkOrderPart(
                    work_order_id=order.id,
                    part_id=part.id,
                    part_name=part.name,
                    quantity=quantity,
                    unit_price=part.unit_price,
                    status=status,
                )
            )

    for row in data.get("technical_notes", []):
        vehicle_id = vehicles[row["vehicle_key"]].id
        existing = db.scalar(
            select(TechnicalNote.id).where(
                TechnicalNote.vehicle_id == vehicle_id,
                TechnicalNote.content == row["content"],
            )
        )
        if existing is None:
            db.add(
                TechnicalNote(
                    vehicle_id=vehicle_id,
                    author_id=users[row["author_key"]].id,
                    content=row["content"],
                )
            )
    synchronize_sequence(
        db,
        "work-order",
        select(WorkOrder.number),
        "OT-",
    )
    synchronize_sequence(
        db,
        "payment",
        select(Payment.receipt_number),
        "CMP-",
    )
    db.commit()
