import asyncio
import hashlib
import json
import secrets
from collections import defaultdict, deque
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from threading import Lock
from time import monotonic
from typing import Annotated

import jwt
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import (
    Appointment,
    AppointmentPartReservation,
    AppointmentSlot,
    AuditLog,
    Customer,
    IdempotencyRecord,
    InventoryMovement,
    Notification,
    Part,
    Payment,
    RefreshSession,
    Service,
    ServicePart,
    Slot,
    Survey,
    TechnicalNote,
    User,
    Vehicle,
    WorkOrder,
    WorkOrderPart,
    WorkOrderService,
)
from app.schemas import (
    AddPartRequest,
    AddServiceRequest,
    AppointmentCreate,
    AssignmentRequest,
    CancelRequest,
    CustomerCreate,
    CustomerUpdate,
    DiagnosisRequest,
    InventoryMovementRequest,
    InternalUserCreate,
    LoginRequest,
    PartCreate,
    PartUpdate,
    PasswordChangeRequest,
    PaymentRequest,
    RegisterRequest,
    RescheduleRequest,
    ServiceCreate,
    ServiceUpdate,
    ServicePartAssignment,
    StatusRequest,
    SurveyRequest,
    VehicleCreate,
    VehicleUpdate,
    WorkOrderCreate,
    UserUpdate,
)
from app.security import (
    hash_password,
    hash_tracking_code,
    issue_token,
    normalize_tracking_code,
    require_roles,
    verify_password,
)
from app.sequences import next_sequence_value
from app.scheduling import (
    FAULT_TYPES,
    allocate_queued_work_orders,
    add_appointment_slots,
    get_appointment_slots,
    get_appointment_parts,
    get_required_slots,
    lock_slots,
    required_slot_count,
    release_work_order_slots,
    slot_start_datetime,
    slots_from_start_map,
)

router = APIRouter(prefix="/api/v1")
Db = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_roles("CUSTOMER", "RECEPTIONIST", "MECHANIC", "ADMIN"))]

ACTIVE_APPOINTMENT_STATES = {"HELD", "CONFIRMED", "RESCHEDULED"}
ACTIVE_WORK_ORDER_STATES = {
    "RECEIVED",
    "ASSIGNED",
    "DIAGNOSING",
    "WAITING_PARTS",
    "PENDING_INSTALLATION",
    "REPAIRING",
    "FINISHED",
    "PENDING_PAYMENT",
    "PAID",
}
TRACKING_REQUESTS: dict[str, deque[float]] = defaultdict(deque)
TRACKING_REQUESTS_LOCK = Lock()
WORK_ORDER_TRANSITIONS = {
    "RECEIVED": {"ASSIGNED", "CANCELLED"},
    "ASSIGNED": {"DIAGNOSING", "CANCELLED"},
    "DIAGNOSING": {"WAITING_PARTS", "REPAIRING", "CANCELLED"},
    "WAITING_PARTS": {"REPAIRING", "PENDING_INSTALLATION", "CANCELLED"},
    "PENDING_INSTALLATION": {"REPAIRING", "CANCELLED"},
    "REPAIRING": {"WAITING_PARTS", "FINISHED", "CANCELLED"},
    "FINISHED": {"PENDING_PAYMENT"},
    "PENDING_PAYMENT": {"PAID"},
    "PAID": {"DELIVERED"},
}


def fail(status_code: int, detail: str) -> None:
    raise HTTPException(status_code=status_code, detail=detail)


def enforce_tracking_rate_limit(client_key: str) -> None:
    now = monotonic()
    with TRACKING_REQUESTS_LOCK:
        requests = TRACKING_REQUESTS[client_key]
        while requests and now - requests[0] >= 60:
            requests.popleft()
        if len(requests) >= 30:
            fail(429, "Demasiadas consultas, espera un momento")
        requests.append(now)


def record_audit(
    db: Session,
    actor: User | None,
    action: str,
    entity: str,
    entity_id: str,
    details: str = "",
) -> None:
    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
        )
    )


def public_user(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "active": user.active,
        "must_change_password": user.must_change_password,
    }


def public_customer(customer: Customer) -> dict[str, object]:
    return {
        "id": customer.id,
        "full_name": customer.full_name,
        "document_type": customer.document_type,
        "document_number": customer.document_number,
        "phone": customer.phone,
        "email": customer.email,
        "data_consent_version": customer.data_consent_version,
    }


def public_work_order(
    order: WorkOrder,
    tracking_code: str | None = None,
) -> dict[str, object]:
    result = {
        column.key: getattr(order, column.key)
        for column in WorkOrder.__mapper__.column_attrs
        if column.key != "tracking_code_hash"
    }
    if tracking_code is not None:
        result["tracking_code"] = tracking_code
    return result


def enforce_csrf_origin(request: Request) -> None:
    allowed_origins = {
        origin.strip()
        for origin in get_settings().cors_origins.split(",")
        if origin.strip()
    }
    if request.headers.get("origin") not in allowed_origins:
        fail(403, "El origen de la solicitud no está autorizado")


def issue_refresh_token(
    db: Session,
    user: User,
    family_id: str | None = None,
) -> str:
    token_id = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    session_family_id = family_id or secrets.token_hex(18)
    db.add(
        RefreshSession(
            user_id=user.id,
            token_id=token_id,
            family_id=session_family_id,
            expires_at=expires,
            revoked=False,
        )
    )
    return jwt.encode(
        {"sub": user.id, "type": "refresh", "jti": token_id, "exp": expires},
        get_settings().jwt_secret,
        algorithm="HS256",
    )


def customer_for_user(db: Session, user: User) -> Customer:
    customer = db.scalar(select(Customer).where(Customer.user_id == user.id))
    if customer is None:
        fail(404, "No se encontró el perfil del cliente")
    return customer


def assert_vehicle_access(db: Session, vehicle_id: str, user: User) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        fail(404, "No se encontró el vehículo")
    if user.role == "CUSTOMER" and vehicle.customer_id != customer_for_user(db, user).id:
        fail(404, "No se encontró el vehículo")
    return vehicle


def appointment_parts(
    db: Session,
    appointment: Appointment,
    *,
    lock: bool = False,
) -> list[tuple[Part, int]]:
    return get_appointment_parts(db, appointment, lock=lock)


def reserve_appointment_parts(
    db: Session,
    appointment: Appointment,
    multiplier: int,
) -> list[tuple[Part, int]]:
    reserved_parts = appointment_parts(db, appointment, lock=True)
    for part, quantity in reserved_parts:
        if multiplier > 0 and part.physical_stock - part.reserved_stock < quantity:
            fail(
                409,
                f"No tenemos {part.name} disponible para este servicio en este momento",
            )
        part.reserved_stock += quantity * multiplier
        if part.reserved_stock < 0:
            fail(409, "La reserva de repuestos no es válida")
    return reserved_parts


def get_owned_appointment(
    db: Session,
    appointment_id: str,
    user: User,
    *,
    lock: bool = False,
) -> Appointment:
    statement = select(Appointment).where(Appointment.id == appointment_id)
    if lock:
        statement = statement.with_for_update()
    appointment = db.scalar(statement)
    if appointment is None:
        fail(404, "No se encontró la cita")
    if user.role == "CUSTOMER" and appointment.customer_id != customer_for_user(db, user).id:
        fail(404, "No se encontró la cita")
    return appointment


def get_work_order(db: Session, order_id: str, user: User | None = None) -> WorkOrder:
    order = db.get(WorkOrder, order_id)
    if order is None:
        fail(404, "No se encontró la orden")
    if user and user.role == "CUSTOMER":
        customer = customer_for_user(db, user)
        if order.customer_id != customer.id:
            fail(404, "No se encontró la orden")
    if user and user.role == "MECHANIC" and order.mechanic_id != user.id:
        fail(403, "No tiene permisos para modificar esta orden")
    return order


def create_order(
    db: Session,
    vehicle: Vehicle,
    customer: Customer,
    fault_description: str,
    appointment: Appointment | None = None,
    service_id: str | None = None,
    fault_type: str | None = None,
) -> tuple[WorkOrder, str]:
    locked_vehicle = db.scalar(
        select(Vehicle)
        .where(Vehicle.id == vehicle.id)
        .with_for_update()
    )
    if locked_vehicle is None:
        fail(404, "No se encontró el vehículo")
    vehicle = locked_vehicle
    active_order = db.scalar(
        select(WorkOrder.id).where(
            WorkOrder.vehicle_id == vehicle.id,
            WorkOrder.status.in_(ACTIVE_WORK_ORDER_STATES),
        )
    )
    if active_order:
        fail(409, "El vehículo ya tiene una orden de trabajo activa")
    selected_service_id = appointment.service_id if appointment else service_id
    service = db.get(Service, selected_service_id) if selected_service_id else None
    if selected_service_id and (service is None or not service.active):
        fail(404, "No se encontró el servicio")
    number = next_sequence_value(
        db,
        "work-order",
        select(WorkOrder.number),
        "OT-",
    )
    tracking_code = "".join(
        secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        for _ in range(10)
    )
    selected_fault_type = next(
        (item for item in FAULT_TYPES if item["code"] == fault_type),
        FAULT_TYPES[2],
    )
    order = WorkOrder(
        number=f"OT-{number:06d}",
        tracking_code_hash=hash_tracking_code(tracking_code),
        appointment_id=appointment.id if appointment else None,
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        status="RECEIVED",
        fault_description=fault_description,
        fault_type=selected_fault_type["code"],
        fault_priority=selected_fault_type["priority"],
        estimated_duration_minutes=service.duration_minutes if service else 60,
    )
    db.add(order)
    db.flush()
    if service:
        db.add(
            WorkOrderService(
                work_order_id=order.id,
                service_name=service.name,
                applied_price=service.price,
            )
        )
    if appointment:
        appointment_slots = get_appointment_slots(db, appointment, lock=True)
        for part, quantity in appointment_parts(db, appointment):
            db.add(
                WorkOrderPart(
                    work_order_id=order.id,
                    part_id=part.id,
                    part_name=part.name,
                    quantity=quantity,
                    unit_price=part.unit_price,
                    status="RESERVED",
                )
            )
        for slot in appointment_slots:
            slot.booked_count = max(0, slot.booked_count - 1)
        appointment.status = "ATTENDED"
    else:
        order.queue_position = 1
    db.flush()
    record_audit(db, None, "WORK_ORDER_CREATED", "work_order", order.id)
    return order, tracking_code


def ensure_slot(db: Session, slot_date: date, start_time: str) -> Slot:
    slot = db.scalar(
        select(Slot).where(Slot.slot_date == slot_date, Slot.start_time == start_time)
    )
    if slot is None:
        slot = Slot(slot_date=slot_date, start_time=start_time, capacity=3, booked_count=0)
        db.add(slot)
        db.flush()
    return slot


def ensure_daily_slots(db: Session, start: date, days: int = 7) -> None:
    for offset in range(days):
        slot_date = start + timedelta(days=offset)
        if slot_date.weekday() == 6:
            continue
        for hour in range(8, 18):
            ensure_slot(db, slot_date, f"{hour:02d}:00")
    db.commit()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "electrostock-api"}


@router.post("/auth/register", status_code=201, response_model=None)
def register(payload: RegisterRequest, db: Db) -> dict[str, object]:
    if not payload.data_consent:
        fail(422, "Debes autorizar el tratamiento de tus datos para crear la cuenta")
    email = str(payload.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        fail(409, "El correo ya se encuentra registrado")
    if db.scalar(
        select(Customer).where(
            Customer.document_type == payload.document_type,
            Customer.document_number == payload.document_number,
        )
    ):
        fail(409, "El documento ya se encuentra registrado")
    user = User(
        full_name=payload.full_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role="CUSTOMER",
    )
    db.add(user)
    db.flush()
    customer = Customer(
        user_id=user.id,
        full_name=user.full_name,
        document_type=payload.document_type,
        document_number=payload.document_number,
        phone=payload.phone,
        email=email,
        data_consent_version="v1",
    )
    db.add(customer)
    db.flush()
    record_audit(db, user, "CUSTOMER_REGISTERED", "customer", customer.id)
    db.commit()
    return {
        "user": public_user(user),
        "customer": public_customer(customer),
        "access_token": issue_token(user),
        "token_type": "bearer",
    }


@router.post("/auth/login", response_model=None)
def login(
    payload: LoginRequest,
    response: Response,
    db: Db,
) -> dict[str, object]:
    user = db.scalar(
        select(User)
        .where(User.email == str(payload.email).lower())
        .with_for_update()
    )
    unauthorized = "Correo o contraseña incorrectos"
    if user is None or not user.active:
        fail(401, "Correo o contraseña incorrectos")
    now = datetime.now(timezone.utc)
    locked_until = user.login_locked_until
    if locked_until and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if locked_until and locked_until > now:
        fail(401, unauthorized)
    if locked_until:
        user.failed_login_attempts = 0
        user.failed_login_started_at = None
        user.login_locked_until = None

    failed_started_at = user.failed_login_started_at
    if failed_started_at and failed_started_at.tzinfo is None:
        failed_started_at = failed_started_at.replace(tzinfo=timezone.utc)
    if failed_started_at is None or now - failed_started_at >= timedelta(minutes=15):
        user.failed_login_attempts = 0
        failed_started_at = now

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        user.failed_login_started_at = failed_started_at
        if user.failed_login_attempts >= 5:
            user.login_locked_until = now + timedelta(minutes=15)
        db.commit()
        fail(401, unauthorized)

    user.failed_login_attempts = 0
    user.failed_login_started_at = None
    user.login_locked_until = None
    refresh_token = issue_refresh_token(db, user)
    record_audit(db, user, "LOGIN", "user", user.id)
    db.commit()
    response.set_cookie(
        "electrostock_refresh",
        refresh_token,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
        max_age=8 * 60 * 60,
        path="/api/v1/auth",
    )
    return {
        "user": public_user(user),
        "access_token": issue_token(user),
        "token_type": "bearer",
        "must_change_password": user.must_change_password,
    }


@router.post("/auth/refresh")
def refresh(
    request: Request,
    response: Response,
    db: Db,
    token: str | None = Cookie(default=None, alias="electrostock_refresh"),
) -> dict[str, str]:
    enforce_csrf_origin(request)
    if not token:
        fail(401, "La sesión de renovación no es válida")
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
        if payload.get("type") != "refresh" or not payload.get("jti"):
            fail(401, "La sesión de renovación no es válida")
        user = db.get(User, payload.get("sub"))
    except jwt.PyJWTError:
        fail(401, "La sesión de renovación no es válida")
    session = db.scalar(
        select(RefreshSession)
        .where(RefreshSession.token_id == payload["jti"])
        .with_for_update()
    )
    if session is None:
        fail(401, "La sesión de renovación no es válida")
    if session.revoked:
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == session.family_id)
            .values(revoked=True)
        )
        db.commit()
        fail(401, "La sesión de renovación no es válida")
    session_expires_at = session.expires_at
    if session_expires_at.tzinfo is None:
        session_expires_at = session_expires_at.replace(tzinfo=timezone.utc)
    if (
        user is None
        or not user.active
        or user.must_change_password
        or session_expires_at <= datetime.now(timezone.utc)
    ):
        fail(401, "La sesión de renovación no es válida")
    session.revoked = True
    next_refresh_token = issue_refresh_token(db, user, session.family_id)
    db.commit()
    response.set_cookie(
        "electrostock_refresh",
        next_refresh_token,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
        max_age=8 * 60 * 60,
        path="/api/v1/auth",
    )
    return {"access_token": issue_token(user), "token_type": "bearer"}


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Db,
    token: str | None = Cookie(default=None, alias="electrostock_refresh"),
) -> Response:
    enforce_csrf_origin(request)
    if token:
        try:
            payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
            session = db.scalar(select(RefreshSession).where(RefreshSession.token_id == payload.get("jti")))
            if session:
                session.revoked = True
                db.commit()
        except jwt.PyJWTError:
            db.rollback()
    response.delete_cookie("electrostock_refresh", path="/api/v1/auth")
    response.status_code = 204
    return response


@router.get("/auth/me", response_model=None)
def me(user: CurrentUser) -> dict[str, object]:
    return public_user(user)


@router.post("/auth/change-password")
def change_password(payload: PasswordChangeRequest, user: CurrentUser, db: Db) -> dict[str, str]:
    if not verify_password(payload.current_password, user.password_hash):
        fail(422, "La contraseña actual no es correcta")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    record_audit(db, user, "PASSWORD_CHANGED", "user", user.id)
    db.commit()
    return {"message": "Contraseña actualizada"}


@router.post("/customers", status_code=201, response_model=None)
def create_customer(
    payload: CustomerCreate,
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
) -> Customer:
    if not payload.data_consent:
        fail(422, "Debe registrar la autorización del cliente para continuar")
    customer = Customer(
        full_name=payload.full_name.strip(),
        document_type=payload.document_type,
        document_number=payload.document_number,
        phone=payload.phone,
        email=str(payload.email).lower() if payload.email else None,
        data_consent_version="v1",
    )
    db.add(customer)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail(409, "El documento ya se encuentra registrado")
    record_audit(db, user, "CUSTOMER_CREATED", "customer", customer.id)
    db.commit()
    return customer


@router.get("/customers", response_model=None)
def list_customers(
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN", "MECHANIC"))],
    db: Db,
    q: str = "",
) -> list[Customer]:
    statement = select(Customer).order_by(Customer.full_name)
    if q:
        statement = statement.where(
            Customer.full_name.ilike(f"%{q}%")
            | Customer.document_number.ilike(f"%{q}%")
        )
    return list(db.scalars(statement.limit(100)))


@router.patch("/customers/{customer_id}", response_model=None)
def update_customer(
    customer_id: str,
    payload: CustomerUpdate,
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        fail(404, "No se encontró el cliente")
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes and changes["email"]:
        changes["email"] = changes["email"].lower()
    if "full_name" in changes and changes["full_name"]:
        changes["full_name"] = changes["full_name"].strip()
    linked_user = db.get(User, customer.user_id) if customer.user_id else None
    if linked_user and "email" in changes and not changes["email"]:
        fail(409, "Una cuenta de cliente debe conservar su correo de acceso")
    if linked_user:
        if "full_name" in changes:
            linked_user.full_name = changes["full_name"]
        if "email" in changes:
            linked_user.email = changes["email"]
    for key, value in changes.items():
        setattr(customer, key, value)
    record_audit(db, user, "CUSTOMER_UPDATED", "customer", customer.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "El documento o correo ya se encuentra registrado")
    return customer


@router.delete("/customers/{customer_id}", status_code=204)
def delete_customer(
    customer_id: str,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> Response:
    customer = db.get(Customer, customer_id)
    if customer is None:
        fail(404, "No se encontró el cliente")
    if customer.user_id:
        fail(409, "No se puede eliminar un cliente con una cuenta de acceso")
    vehicle_count = db.scalar(
        select(func.count()).select_from(Vehicle).where(Vehicle.customer_id == customer.id)
    ) or 0
    if vehicle_count:
        fail(409, "No se puede eliminar un cliente que tiene vehículos registrados")
    record_audit(db, user, "CUSTOMER_DELETED", "customer", customer.id)
    db.delete(customer)
    db.commit()
    return Response(status_code=204)


@router.post("/vehicles", status_code=201, response_model=None)
def create_vehicle(payload: VehicleCreate, user: CurrentUser, db: Db) -> Vehicle:
    if user.role == "CUSTOMER":
        customer = customer_for_user(db, user)
    else:
        if not payload.customer_id:
            fail(422, "Debe seleccionar el cliente del vehículo")
        customer = db.get(Customer, payload.customer_id)
        if customer is None:
            fail(404, "No se encontró el cliente")
    vehicle = Vehicle(
        customer_id=customer.id,
        serial_number=payload.serial_number.strip().upper(),
        plate=payload.plate.strip().upper() if payload.plate else None,
        brand=payload.brand.strip(),
        model=payload.model.strip(),
        year=payload.year,
        battery_capacity_ah=payload.battery_capacity_ah,
        cell_type=payload.cell_type,
        motor_power_w=payload.motor_power_w,
        controller=payload.controller,
    )
    db.add(vehicle)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail(409, "El número de serie o la placa ya se encuentra registrado")
    record_audit(db, user, "VEHICLE_CREATED", "vehicle", vehicle.id)
    db.commit()
    return vehicle


@router.patch("/vehicles/{vehicle_id}", response_model=None)
def update_vehicle(
    vehicle_id: str,
    payload: VehicleUpdate,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> Vehicle:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        fail(404, "No se encontró el vehículo")
    changes = payload.model_dump(exclude_unset=True)
    if "customer_id" in changes:
        customer = db.get(Customer, changes["customer_id"])
        if customer is None:
            fail(404, "No se encontró el cliente")
        if customer.id != vehicle.customer_id:
            has_appointments = db.scalar(
                select(func.count()).select_from(Appointment).where(Appointment.vehicle_id == vehicle.id)
            ) or 0
            has_work_orders = db.scalar(
                select(func.count()).select_from(WorkOrder).where(WorkOrder.vehicle_id == vehicle.id)
            ) or 0
            has_notes = db.scalar(
                select(func.count()).select_from(TechnicalNote).where(TechnicalNote.vehicle_id == vehicle.id)
            ) or 0
            if has_appointments or has_work_orders or has_notes:
                fail(409, "No se puede cambiar el propietario de un vehículo con historial")
    if "serial_number" in changes and changes["serial_number"]:
        changes["serial_number"] = changes["serial_number"].strip().upper()
    if "plate" in changes and changes["plate"]:
        changes["plate"] = changes["plate"].strip().upper()
    if "brand" in changes and changes["brand"]:
        changes["brand"] = changes["brand"].strip()
    if "model" in changes and changes["model"]:
        changes["model"] = changes["model"].strip()
    for key, value in changes.items():
        setattr(vehicle, key, value)
    record_audit(db, user, "VEHICLE_UPDATED", "vehicle", vehicle.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "El número de serie o la placa ya se encuentra registrado")
    return vehicle


@router.delete("/vehicles/{vehicle_id}", status_code=204)
def delete_vehicle(
    vehicle_id: str,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> Response:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        fail(404, "No se encontró el vehículo")
    has_appointments = db.scalar(
        select(func.count()).select_from(Appointment).where(Appointment.vehicle_id == vehicle.id)
    ) or 0
    has_work_orders = db.scalar(
        select(func.count()).select_from(WorkOrder).where(WorkOrder.vehicle_id == vehicle.id)
    ) or 0
    has_notes = db.scalar(
        select(func.count()).select_from(TechnicalNote).where(TechnicalNote.vehicle_id == vehicle.id)
    ) or 0
    if has_appointments or has_work_orders or has_notes:
        fail(409, "No se puede eliminar un vehículo con citas, órdenes o notas técnicas")
    record_audit(db, user, "VEHICLE_DELETED", "vehicle", vehicle.id)
    db.delete(vehicle)
    db.commit()
    return Response(status_code=204)


@router.get("/vehicles/mine", response_model=None)
def my_vehicles(user: CurrentUser, db: Db) -> list[Vehicle]:
    if user.role != "CUSTOMER":
        fail(403, "Esta consulta está disponible para clientes")
    customer = customer_for_user(db, user)
    return list(db.scalars(select(Vehicle).where(Vehicle.customer_id == customer.id)))


@router.get("/vehicles", response_model=None)
def search_vehicles(
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN", "MECHANIC"))],
    db: Db,
    q: str = "",
) -> list[Vehicle]:
    statement = select(Vehicle).order_by(Vehicle.serial_number)
    if q:
        statement = statement.where(
            Vehicle.serial_number.ilike(f"%{q}%")
            | Vehicle.plate.ilike(f"%{q}%")
            | Vehicle.model.ilike(f"%{q}%")
        )
    return list(db.scalars(statement.limit(100)))


@router.get("/vehicles/{vehicle_id}/record", response_model=None)
def technical_record(vehicle_id: str, user: CurrentUser, db: Db) -> dict[str, object]:
    vehicle = assert_vehicle_access(db, vehicle_id, user)
    notes = list(
        db.scalars(
            select(TechnicalNote)
            .where(TechnicalNote.vehicle_id == vehicle.id)
            .order_by(TechnicalNote.created_at.desc())
        )
    )
    orders = list(
        db.scalars(
            select(WorkOrder)
            .where(WorkOrder.vehicle_id == vehicle.id)
            .order_by(WorkOrder.created_at.desc())
        )
    )
    return {
        "vehicle": vehicle,
        "notes": notes,
        "work_orders": [public_work_order(order) for order in orders],
    }


@router.post("/vehicles/{vehicle_id}/notes", status_code=201, response_model=None)
def add_technical_note(
    vehicle_id: str,
    payload: DiagnosisRequest,
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN", "MECHANIC"))],
    db: Db,
) -> TechnicalNote:
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        fail(404, "No se encontró el vehículo")
    note = TechnicalNote(vehicle_id=vehicle.id, author_id=user.id, content=payload.diagnosis)
    db.add(note)
    record_audit(db, user, "TECHNICAL_NOTE_ADDED", "vehicle", vehicle.id)
    db.commit()
    return note


@router.get("/catalog/services", response_model=None)
def list_services(db: Db, active: bool | None = True) -> list[Service]:
    statement = select(Service).order_by(Service.name)
    if active is not None:
        statement = statement.where(Service.active.is_(active))
    return list(db.scalars(statement))


@router.post("/catalog/services", status_code=201, response_model=None)
def create_service(
    payload: ServiceCreate,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> Service:
    service = Service(**payload.model_dump())
    db.add(service)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail(409, "El código del servicio ya existe")
    record_audit(db, user, "SERVICE_CREATED", "service", service.id)
    db.commit()
    return service


@router.patch("/catalog/services/{service_id}", response_model=None)
def update_service(
    service_id: str,
    payload: ServiceUpdate,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> Service:
    service = db.get(Service, service_id)
    if service is None:
        fail(404, "No se encontró el servicio")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(service, key, value)
    record_audit(db, user, "SERVICE_UPDATED", "service", service.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "El código del servicio ya existe")
    return service


@router.post("/catalog/services/{service_id}/deactivate")
def deactivate_service(
    service_id: str,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> dict[str, str]:
    service = db.get(Service, service_id)
    if service is None:
        fail(404, "No se encontró el servicio")
    service.active = False
    record_audit(db, user, "SERVICE_DEACTIVATED", "service", service.id)
    db.commit()
    return {"message": "Servicio desactivado"}


@router.get("/catalog/services/{service_id}/parts", response_model=None)
def service_parts(service_id: str, db: Db) -> list[dict[str, object]]:
    if db.get(Service, service_id) is None:
        fail(404, "No se encontró el servicio")
    rows = db.execute(
        select(ServicePart, Part)
        .join(Part, ServicePart.part_id == Part.id)
        .where(ServicePart.service_id == service_id)
    ).all()
    return [
        {
            "id": link.id,
            "part": {
                column.key: getattr(part, column.key)
                for column in Part.__mapper__.column_attrs
            },
            "quantity": link.quantity,
        }
        for link, part in rows
    ]


@router.put("/catalog/services/{service_id}/parts")
def set_service_parts(
    service_id: str,
    payload: list[ServicePartAssignment],
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> dict[str, object]:
    service = db.scalar(
        select(Service)
        .where(Service.id == service_id)
        .with_for_update()
    )
    if service is None:
        fail(404, "No se encontró el servicio")
    part_ids = [row.part_id for row in payload]
    if len(set(part_ids)) != len(part_ids):
        fail(422, "No se puede asociar el mismo repuesto más de una vez")
    validated: list[tuple[str, int]] = []
    for row in payload:
        part = db.get(Part, row.part_id)
        if part is None or not part.active:
            fail(422, "Cada repuesto debe existir y estar activo")
        validated.append((row.part_id, row.quantity))

    preserved_reservations = db.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.service_id == service.id,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATES),
        )
    ) or 0
    db.query(ServicePart).filter(ServicePart.service_id == service_id).delete()
    for part_id, quantity in validated:
        db.add(ServicePart(service_id=service_id, part_id=part_id, quantity=quantity))
    record_audit(
        db,
        user,
        "SERVICE_PARTS_UPDATED",
        "service",
        service_id,
        f"preserved_appointment_reservations={preserved_reservations}",
    )
    db.commit()
    return {
        "parts": service_parts(service_id, db),
        "preserved_appointment_reservations": preserved_reservations,
    }


@router.get("/catalog/fault-types")
def fault_types() -> list[dict[str, str]]:
    return list(FAULT_TYPES)


@router.get("/inventory/parts")
def list_parts(
    user: Annotated[User, Depends(require_roles("ADMIN", "MECHANIC", "RECEPTIONIST"))],
    db: Db,
    category: str | None = None,
    alerts_only: bool = False,
    active: bool | None = True,
) -> list[dict[str, object]]:
    statement = select(Part).order_by(Part.name)
    if active is not None:
        statement = statement.where(Part.active.is_(active))
    if category:
        statement = statement.where(Part.category == category)
    parts = list(db.scalars(statement))
    if alerts_only:
        parts = [part for part in parts if part.physical_stock - part.reserved_stock <= part.min_threshold]
    return [
        {
            "id": part.id,
            "sku": part.sku,
            "name": part.name,
            "category": part.category,
            "voltage": part.voltage,
            "unit_price": part.unit_price,
            "physical_stock": part.physical_stock,
            "reserved_stock": part.reserved_stock,
            "available_stock": part.physical_stock - part.reserved_stock,
            "min_threshold": part.min_threshold,
            "active": part.active,
        }
        for part in parts
    ]


@router.post("/inventory/parts", status_code=201, response_model=None)
def create_part(
    payload: PartCreate,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> Part:
    part = Part(**payload.model_dump())
    initial_stock = part.physical_stock
    part.physical_stock = 0
    db.add(part)
    db.flush()
    if initial_stock:
        part.physical_stock = initial_stock
        db.add(
            InventoryMovement(
                part_id=part.id,
                movement_type="IN",
                quantity=initial_stock,
                reason="Existencia inicial",
            )
        )
    record_audit(db, user, "PART_CREATED", "part", part.id)
    db.commit()
    return part


@router.get("/inventory/parts/search")
def search_parts(
    user: Annotated[User, Depends(require_roles("MECHANIC"))],
    db: Db,
    q: str = Query(min_length=1, max_length=100),
) -> list[dict[str, object]]:
    search = f"%{q.strip()}%"
    parts = db.scalars(
        select(Part)
        .where(
            Part.active.is_(True),
            Part.name.ilike(search) | Part.sku.ilike(search),
        )
        .order_by(Part.name)
        .limit(50)
    )
    return [
        {
            "id": part.id,
            "sku": part.sku,
            "name": part.name,
            "unit_price": part.unit_price,
            "available_stock": part.physical_stock - part.reserved_stock,
        }
        for part in parts
        if part.physical_stock > part.reserved_stock
    ]


@router.patch("/inventory/parts/{part_id}", response_model=None)
def update_part(
    part_id: str,
    payload: PartUpdate,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> Part:
    part = db.get(Part, part_id)
    if part is None:
        fail(404, "No se encontró el repuesto")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("active") is False and part.reserved_stock:
        fail(409, "No se puede desactivar un repuesto con reservas activas")
    for key, value in changes.items():
        setattr(part, key, value)
    record_audit(db, user, "PART_UPDATED", "part", part.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "El código SKU ya se encuentra registrado")
    return part


@router.post("/inventory/parts/{part_id}/deactivate")
def deactivate_part(
    part_id: str,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> dict[str, str]:
    part = db.get(Part, part_id)
    if part is None:
        fail(404, "No se encontró el repuesto")
    if part.reserved_stock:
        fail(409, "No se puede desactivar un repuesto con reservas activas")
    part.active = False
    record_audit(db, user, "PART_DEACTIVATED", "part", part.id)
    db.commit()
    return {"message": "Repuesto desactivado"}


@router.patch("/inventory/parts/{part_id}/threshold", response_model=None)
def update_part_threshold(
    part_id: str,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
    min_threshold: int = Query(ge=0),
) -> Part:
    part = db.get(Part, part_id)
    if part is None:
        fail(404, "No se encontró el repuesto")
    part.min_threshold = min_threshold
    record_audit(db, user, "PART_THRESHOLD_UPDATED", "part", part.id)
    db.commit()
    return part


@router.post("/inventory/movements", status_code=201, response_model=None)
def inventory_movement(
    payload: InventoryMovementRequest,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> InventoryMovement:
    part = db.get(Part, payload.part_id)
    if part is None or not part.active:
        fail(404, "No se encontró el repuesto")
    if payload.type == "IN":
        part.physical_stock += payload.quantity
    elif payload.type == "WRITE_OFF":
        if part.physical_stock - payload.quantity < part.reserved_stock:
            fail(409, "No se puede dar de baja una cantidad superior al stock no reservado")
        part.physical_stock -= payload.quantity
    else:
        new_stock = payload.quantity
        if new_stock < part.reserved_stock:
            fail(409, "El ajuste no puede dejar el stock por debajo de lo reservado")
        part.physical_stock = new_stock
    movement = InventoryMovement(
        part_id=part.id,
        movement_type=payload.type,
        quantity=payload.quantity,
        reason=payload.reason,
    )
    db.add(movement)
    record_audit(db, user, "INVENTORY_MOVEMENT", "part", part.id, payload.type)
    db.commit()
    return movement


@router.get("/scheduling/occupancy", response_model=None)
def get_occupancy(
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
    month: str = Query(pattern=r"^\d{4}-\d{2}$"),
) -> list[dict[str, object]]:
    try:
        year, month_number = (int(value) for value in month.split("-"))
        start = date(year, month_number, 1)
    except ValueError:
        fail(422, "El mes debe tener un formato válido (AAAA-MM)")
    end = date(year + (month_number == 12), month_number % 12 + 1, 1)
    slots = db.scalars(
        select(Slot)
        .where(Slot.slot_date >= start, Slot.slot_date < end)
        .order_by(Slot.slot_date, Slot.start_time)
    )
    return [
        {
            "id": slot.id,
            "date": slot.slot_date,
            "start_time": slot.start_time,
            "capacity": slot.capacity,
            "booked_count": slot.booked_count,
            "available": slot.capacity - slot.booked_count,
            "blocked_reason": slot.blocked_reason,
        }
        for slot in slots
    ]


@router.get("/scheduling/day", response_model=None)
def get_scheduling_day(
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
    day: date = Query(alias="date"),
) -> dict[str, object]:
    slots = list(
        db.scalars(
            select(Slot).where(Slot.slot_date == day).order_by(Slot.start_time)
        )
    )
    appointments = list(
        db.scalars(
            select(Appointment)
            .join(Slot, Appointment.slot_id == Slot.id)
            .where(Slot.slot_date == day)
            .order_by(Slot.start_time)
        )
    )
    queue = list(
        db.scalars(
            select(WorkOrder)
                .where(
                    WorkOrder.status == "RECEIVED",
                    WorkOrder.queue_position.is_not(None),
                )
                .order_by(WorkOrder.queue_position, WorkOrder.created_at)
        )
    )
    return {"date": day, "slots": slots, "appointments": appointments, "queue": queue}


@router.get("/scheduling/availability")
def availability(
    db: Db,
    service_id: str | None = None,
    date_from: date = Query(default_factory=date.today, alias="from"),
    days: int = Query(default=7, ge=1, le=30),
) -> list[dict[str, object]]:
    service = db.get(Service, service_id) if service_id else None
    if service_id and (service is None or not service.active):
        fail(404, "No se encontró el servicio")
    duration_minutes = service.duration_minutes if service else 60
    ensure_daily_slots(db, date_from, days)
    slots = list(
        db.scalars(
            select(Slot)
            .where(Slot.slot_date >= date_from, Slot.slot_date < date_from + timedelta(days=days))
            .order_by(Slot.slot_date, Slot.start_time)
        )
    )
    slots_by_start = {
        (slot.slot_date, slot.start_time): slot
        for slot in slots
    }
    available_slots = []
    for slot in slots:
        if slot_start_datetime(slot) <= datetime.now(slot_start_datetime(slot).tzinfo):
            continue
        required = slots_from_start_map(slot, duration_minutes, slots_by_start)
        if len(required) != required_slot_count(duration_minutes):
            continue
        if any(
            candidate.blocked_reason
            or candidate.booked_count >= candidate.capacity
            for candidate in required
        ):
            continue
        available_slots.append(
            {
                "id": slot.id,
                "date": slot.slot_date,
                "start_time": slot.start_time,
                "capacity": min(candidate.capacity for candidate in required),
                "available": min(
                    candidate.capacity - candidate.booked_count
                    for candidate in required
                ),
                "blocked": False,
                "blocked_reason": None,
            }
        )
    return available_slots


@router.post("/scheduling/appointments", status_code=201, response_model=None)
def create_appointment(payload: AppointmentCreate, user: CurrentUser, db: Db) -> Appointment:
    if user.role != "CUSTOMER":
        fail(403, "Solo los clientes pueden agendar una cita")
    customer = customer_for_user(db, user)
    vehicle = db.scalar(
        select(Vehicle)
        .where(Vehicle.id == payload.vehicle_id)
        .with_for_update()
    )
    if vehicle is None:
        fail(404, "No se encontró el vehículo")
    if vehicle.customer_id != customer.id:
        fail(404, "No se encontró el vehículo")
    service = db.get(Service, payload.service_id)
    slot = db.get(Slot, payload.slot_id)
    if service is None or not service.active:
        fail(404, "No se encontró el servicio")
    if slot is None:
        fail(404, "No se encontró la franja")
    if slot_start_datetime(slot) <= datetime.now(slot_start_datetime(slot).tzinfo):
        fail(409, "No se puede agendar una cita en una franja que ya inició")
    required_slots = get_required_slots(
        db,
        slot,
        service.duration_minutes,
        lock=True,
    )
    if (
        len(required_slots) != required_slot_count(service.duration_minutes)
        or any(
            candidate.blocked_reason
            or candidate.booked_count >= candidate.capacity
            for candidate in required_slots
        )
    ):
        fail(409, "Alguien acaba de tomar este cupo")
    existing = db.scalar(
        select(Appointment).where(
            Appointment.vehicle_id == vehicle.id,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATES),
        )
    )
    if existing:
        fail(409, "El vehículo ya tiene una cita activa")
    appointment = Appointment(
        code=f"CITA-{slot.slot_date:%Y%m%d}-{secrets.randbelow(9000) + 1000}",
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        service_id=service.id,
        slot_id=slot.id,
        status="HELD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    reserved_parts = reserve_appointment_parts(db, appointment, 1)
    db.add(appointment)
    db.flush()
    add_appointment_slots(db, appointment, required_slots)
    db.add_all(
        AppointmentPartReservation(
            appointment_id=appointment.id,
            part_id=part.id,
            quantity=quantity,
        )
        for part, quantity in reserved_parts
    )
    for required_slot in required_slots:
        required_slot.booked_count += 1
    record_audit(db, user, "BOOKING_STARTED", "appointment", appointment.id)
    db.commit()
    return appointment


@router.post("/scheduling/appointments/{appointment_id}/confirm", response_model=None)
def confirm_appointment(appointment_id: str, user: CurrentUser, db: Db) -> Appointment:
    appointment = get_owned_appointment(db, appointment_id, user, lock=True)
    if appointment.status != "HELD":
        fail(409, "La cita ya no está pendiente de confirmación")
    appointment.status = "CONFIRMED"
    appointment.expires_at = None
    record_audit(db, user, "APPOINTMENT_CONFIRMED", "appointment", appointment.id)
    db.commit()
    return appointment


@router.post("/scheduling/appointments/{appointment_id}/cancel", response_model=None)
def cancel_appointment(
    appointment_id: str,
    payload: CancelRequest,
    user: CurrentUser,
    db: Db,
) -> Appointment:
    appointment = get_owned_appointment(db, appointment_id, user, lock=True)
    if appointment.status not in ACTIVE_APPOINTMENT_STATES:
        fail(409, "La cita no se puede cancelar en su estado actual")
    appointment_slots = get_appointment_slots(db, appointment, lock=True)
    reserve_appointment_parts(db, appointment, -1)
    for slot in appointment_slots:
        slot.booked_count = max(0, slot.booked_count - 1)
    appointment.status = "CANCELLED"
    appointment.cancel_reason = payload.reason
    record_audit(db, user, "APPOINTMENT_CANCELLED", "appointment", appointment.id, payload.reason)
    allocate_queued_work_orders(db)
    db.commit()
    return appointment


@router.post("/scheduling/appointments/{appointment_id}/reschedule", response_model=None)
def reschedule_appointment(
    appointment_id: str,
    payload: RescheduleRequest,
    user: CurrentUser,
    db: Db,
) -> Appointment:
    appointment = get_owned_appointment(db, appointment_id, user, lock=True)
    if appointment.status not in ACTIVE_APPOINTMENT_STATES:
        fail(409, "La cita no se puede reprogramar en su estado actual")
    service = db.get(Service, appointment.service_id)
    new_start_slot = db.get(Slot, payload.slot_id)
    if service is None or new_start_slot is None:
        fail(404, "No se encontró el servicio o la franja")
    old_slots = get_appointment_slots(db, appointment)
    old_start_slot = db.get(Slot, appointment.slot_id)
    if old_start_slot is None:
        fail(409, "La cita no tiene una franja válida")
    current_time = datetime.now(slot_start_datetime(old_start_slot).tzinfo)
    if slot_start_datetime(old_start_slot) - current_time <= timedelta(hours=1):
        fail(409, "Solo puedes reprogramar una cita con más de una hora de anticipación")
    if slot_start_datetime(new_start_slot) <= current_time:
        fail(409, "No se puede reprogramar a una franja que ya inició")
    target_slots = get_required_slots(
        db,
        new_start_slot,
        service.duration_minutes,
    )
    if len(target_slots) != required_slot_count(service.duration_minutes):
        fail(409, "Alguien acaba de tomar este cupo")
    locked_slots = lock_slots(
        db,
        {slot.id for slot in old_slots + target_slots},
    )
    locked_by_id = {slot.id: slot for slot in locked_slots}
    old_slots = [locked_by_id[slot.id] for slot in old_slots]
    target_slots = [locked_by_id[slot.id] for slot in target_slots]
    old_slot_ids = {slot.id for slot in old_slots}
    if any(
        slot.blocked_reason
        or slot.booked_count - (slot.id in old_slot_ids) >= slot.capacity
        for slot in target_slots
    ):
        fail(409, "Alguien acaba de tomar este cupo")
    for slot in old_slots:
        slot.booked_count = max(0, slot.booked_count - 1)
    for slot in target_slots:
        slot.booked_count += 1
    db.execute(
        delete(AppointmentSlot).where(
            AppointmentSlot.appointment_id == appointment.id
        )
    )
    add_appointment_slots(db, appointment, target_slots)
    appointment.slot_id = new_start_slot.id
    appointment.status = "RESCHEDULED"
    record_audit(db, user, "APPOINTMENT_RESCHEDULED", "appointment", appointment.id)
    allocate_queued_work_orders(db)
    db.commit()
    return appointment


@router.get("/scheduling/appointments/mine", response_model=None)
def my_appointments(user: CurrentUser, db: Db) -> list[Appointment]:
    if user.role != "CUSTOMER":
        fail(403, "Esta consulta está disponible para clientes")
    customer = customer_for_user(db, user)
    return list(
        db.scalars(
            select(Appointment)
            .where(Appointment.customer_id == customer.id)
            .order_by(Appointment.created_at.desc())
        )
    )


@router.get("/scheduling/appointments", response_model=None)
def find_appointment(
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
    code: str | None = None,
    vehicle_id: str | None = None,
) -> list[Appointment]:
    statement = select(Appointment)
    if code:
        statement = statement.where(Appointment.code == code)
    if vehicle_id:
        statement = statement.where(Appointment.vehicle_id == vehicle_id)
    return list(db.scalars(statement.limit(100)))


@router.post("/scheduling/slots/{slot_id}/block", response_model=None)
def block_slot(
    slot_id: str,
    payload: CancelRequest,
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
) -> dict[str, object]:
    if not payload.reason.strip():
        fail(422, "El motivo del bloqueo es obligatorio")
    slot = db.get(Slot, slot_id)
    if slot is None:
        fail(404, "No se encontró la franja")
    slot.blocked_reason = payload.reason.strip()
    record_audit(db, user, "SLOT_BLOCKED", "slot", slot.id, payload.reason)
    db.commit()
    affected_appointments = list(
        db.scalars(
            select(Appointment)
            .outerjoin(
                AppointmentSlot,
                AppointmentSlot.appointment_id == Appointment.id,
            )
            .where(
                or_(
                    Appointment.slot_id == slot.id,
                    AppointmentSlot.slot_id == slot.id,
                )
            )
            .distinct()
        )
    )
    return {"slot": slot, "affected_appointments": affected_appointments}


@router.post("/scheduling/slots/{slot_id}/unblock", response_model=None)
def unblock_slot(
    slot_id: str,
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
) -> Slot:
    slot = db.get(Slot, slot_id)
    if slot is None:
        fail(404, "No se encontró la franja")
    slot.blocked_reason = None
    record_audit(db, user, "SLOT_UNBLOCKED", "slot", slot.id)
    allocate_queued_work_orders(db)
    db.commit()
    return slot


@router.post("/scheduling/walk-ins", status_code=201, response_model=None)
def create_walk_in(
    payload: WorkOrderCreate,
    response: Response,
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=80,
    ),
) -> dict[str, object]:
    request_hash = hashlib.sha256(
        json.dumps(
            payload.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    existing_request = db.get(
        IdempotencyRecord,
        ("walk-in", idempotency_key),
    )
    if existing_request:
        if existing_request.request_hash != request_hash:
            fail(409, "La clave de idempotencia ya se utilizó con otra solicitud")
        existing_order = db.get(WorkOrder, existing_request.resource_id)
        if existing_order is None:
            fail(409, "La solicitud idempotente ya no tiene una orden disponible")
        response.status_code = 200
        return public_work_order(existing_order)

    if not payload.vehicle_id:
        fail(422, "Debe seleccionar un vehículo")
    if not payload.service_id:
        fail(422, "Debe seleccionar el servicio del ingreso")
    if not payload.fault_type:
        fail(422, "Debe seleccionar el tipo de falla del ingreso")
    vehicle = db.scalar(
        select(Vehicle)
        .where(Vehicle.id == payload.vehicle_id)
        .with_for_update()
    )
    if vehicle is None:
        fail(404, "No se encontró el vehículo")
    customer = db.get(Customer, payload.customer_id or vehicle.customer_id)
    if customer is None or customer.id != vehicle.customer_id:
        fail(422, "El cliente no corresponde al vehículo")
    active_appointment = db.scalar(
        select(Appointment).where(
            Appointment.vehicle_id == vehicle.id,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATES),
        )
    )
    if active_appointment:
        fail(409, "El vehículo tiene una cita activa; crea la orden desde esa cita")
    order, tracking_code = create_order(
        db,
        vehicle,
        customer,
        payload.fault_description,
        service_id=payload.service_id,
        fault_type=payload.fault_type,
    )
    allocate_queued_work_orders(db)
    record_audit(db, user, "WALK_IN_CREATED", "work_order", order.id)
    db.add(
        IdempotencyRecord(
            scope="walk-in",
            key=idempotency_key,
            request_hash=request_hash,
            resource_id=order.id,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_request = db.get(
            IdempotencyRecord,
            ("walk-in", idempotency_key),
        )
        if existing_request is None:
            raise
        if existing_request.request_hash != request_hash:
            fail(409, "La clave de idempotencia ya se utilizó con otra solicitud")
        existing_order = db.get(WorkOrder, existing_request.resource_id)
        if existing_order is None:
            fail(409, "La solicitud idempotente ya no tiene una orden disponible")
        response.status_code = 200
        return public_work_order(existing_order)
    return public_work_order(order, tracking_code)


@router.get("/scheduling/walk-ins/queue", response_model=None)
def walk_in_queue(
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
) -> list[dict[str, object]]:
    return [
        public_work_order(order)
        for order in db.scalars(
            select(WorkOrder)
            .where(
                WorkOrder.status == "RECEIVED",
                WorkOrder.queue_position.is_not(None),
            )
            .order_by(WorkOrder.queue_position, WorkOrder.created_at)
        )
    ]


@router.post("/work-orders", status_code=201, response_model=None)
def create_work_order(
    payload: WorkOrderCreate,
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
) -> dict[str, object]:
    if payload.appointment_code:
        appointment = db.scalar(
            select(Appointment)
            .where(Appointment.code == payload.appointment_code)
            .with_for_update()
        )
        if appointment is None or appointment.status not in ACTIVE_APPOINTMENT_STATES:
            fail(404, "No se encontró una cita activa con ese código")
        vehicle = db.get(Vehicle, appointment.vehicle_id)
        customer = db.get(Customer, appointment.customer_id)
        if vehicle is None or customer is None:
            fail(409, "La cita no tiene un vehículo o cliente válido")
        order, tracking_code = create_order(
            db,
            vehicle,
            customer,
            payload.fault_description,
            appointment,
            payload.service_id,
            payload.fault_type,
        )
    else:
        if not payload.vehicle_id:
            fail(422, "Debe seleccionar una cita o un vehículo")
        vehicle = db.scalar(
            select(Vehicle)
            .where(Vehicle.id == payload.vehicle_id)
            .with_for_update()
        )
        if vehicle is None:
            fail(404, "No se encontró el vehículo")
        customer = db.get(Customer, payload.customer_id or vehicle.customer_id)
        if customer is None or customer.id != vehicle.customer_id:
            fail(422, "El cliente no corresponde al vehículo")
        active_appointment = db.scalar(
            select(Appointment)
            .where(
                Appointment.vehicle_id == vehicle.id,
                Appointment.status.in_(ACTIVE_APPOINTMENT_STATES),
            )
            .with_for_update()
        )
        if active_appointment:
            fail(409, "El vehículo tiene una cita activa; crea la orden desde esa cita")
        order, tracking_code = create_order(
            db,
            vehicle,
            customer,
            payload.fault_description,
            service_id=payload.service_id,
            fault_type=payload.fault_type,
        )
    if order.appointment_id is None:
        allocate_queued_work_orders(db)
    record_audit(db, user, "WORK_ORDER_CREATED", "work_order", order.id)
    db.commit()
    return public_work_order(order, tracking_code)


@router.get("/work-orders", response_model=None)
def list_work_orders(
    user: Annotated[User, Depends(require_roles("ADMIN", "RECEPTIONIST", "MECHANIC"))],
    db: Db,
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = None,
) -> list[dict[str, object]]:
    statement = select(WorkOrder).order_by(WorkOrder.created_at.desc())
    if user.role == "MECHANIC":
        statement = statement.where(WorkOrder.mechanic_id == user.id)
    if status_filter:
        statement = statement.where(WorkOrder.status == status_filter.upper())
    if q:
        statement = statement.where(
            WorkOrder.number.ilike(f"%{q}%")
        )
    return [public_work_order(order) for order in db.scalars(statement.limit(200))]


@router.get("/work-orders/mine", response_model=None)
def mechanic_orders(
    user: Annotated[User, Depends(require_roles("MECHANIC"))],
    db: Db,
) -> list[dict[str, object]]:
    return [
        public_work_order(order)
        for order in db.scalars(
            select(WorkOrder)
            .where(WorkOrder.mechanic_id == user.id)
            .order_by(WorkOrder.created_at)
        )
    ]


@router.get("/work-orders/{order_id}", response_model=None)
def work_order_detail(order_id: str, user: CurrentUser, db: Db) -> dict[str, object]:
    order = get_work_order(db, order_id, user)
    return {
        "order": public_work_order(order),
        "services": list(db.scalars(select(WorkOrderService).where(WorkOrderService.work_order_id == order.id))),
        "parts": list(db.scalars(select(WorkOrderPart).where(WorkOrderPart.work_order_id == order.id))),
    }


@router.patch("/work-orders/{order_id}/assignment", response_model=None)
def assign_mechanic(
    order_id: str,
    payload: AssignmentRequest,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> dict[str, object]:
    order = db.scalar(select(WorkOrder).where(WorkOrder.id == order_id).with_for_update())
    if order is None:
        fail(404, "No se encontró la orden")
    if order.version != payload.version:
        fail(409, "La orden ha sido modificada por otro usuario, por favor actualice la página")
    mechanic = db.get(User, payload.mechanic_id)
    if mechanic is None or not mechanic.active or mechanic.role != "MECHANIC":
        fail(409, "El mecánico seleccionado no se encuentra activo o disponible")
    if order.status == "RECEIVED":
        release_work_order_slots(db, order, lock=True)
        order.status = "ASSIGNED"
    elif order.status not in {"ASSIGNED", "DIAGNOSING", "WAITING_PARTS", "REPAIRING"}:
        fail(409, "La orden no se puede asignar en su estado actual")
    order.mechanic_id = mechanic.id
    order.version += 1
    allocate_queued_work_orders(db)
    record_audit(db, user, "WORK_ORDER_ASSIGNED", "work_order", order.id, mechanic.id)
    db.commit()
    return public_work_order(order)


@router.patch("/work-orders/{order_id}/status", response_model=None)
def change_work_order_status(
    order_id: str,
    payload: StatusRequest,
    user: CurrentUser,
    db: Db,
) -> dict[str, object]:
    order = db.scalar(select(WorkOrder).where(WorkOrder.id == order_id).with_for_update())
    if order is None:
        fail(404, "No se encontró la orden")
    if user.role == "MECHANIC" and order.mechanic_id != user.id:
        record_audit(db, user, "ACCESS_DENIED", "work_order", order.id)
        db.commit()
        fail(403, "No tiene permisos para modificar esta orden")
    target = payload.status.upper()
    if target not in WORK_ORDER_TRANSITIONS.get(order.status, set()):
        allowed = ", ".join(sorted(WORK_ORDER_TRANSITIONS.get(order.status, set()))) or "ninguno"
        fail(409, f"Esta orden no puede pasar de {order.status} a {target}. Pasos válidos: {allowed}")
    if target == "PENDING_INSTALLATION":
        if not payload.reason or not payload.expected_part_id:
            fail(422, "Debe indicar el motivo y el repuesto esperado")
        if db.get(Part, payload.expected_part_id) is None:
            fail(422, "El repuesto esperado no existe")
        order.expected_part_id = payload.expected_part_id
        order.expected_part_date = payload.expected_part_date
    if target == "CANCELLED":
        if order.status == "PENDING_INSTALLATION" and not payload.reason:
            fail(422, "Debe indicar el motivo para cancelar una orden pendiente")
        for line in db.scalars(
            select(WorkOrderPart).where(
                WorkOrderPart.work_order_id == order.id,
                WorkOrderPart.status == "RESERVED",
            )
        ):
            part = db.get(Part, line.part_id)
            if part:
                part.reserved_stock = max(0, part.reserved_stock - line.quantity)
            line.status = "RETURNED"
        release_work_order_slots(db, order, lock=True)
    if target == "FINISHED":
        reserved_lines = db.scalar(
            select(func.count()).select_from(WorkOrderPart).where(
                WorkOrderPart.work_order_id == order.id,
                WorkOrderPart.status == "RESERVED",
            )
        )
        if reserved_lines:
            fail(409, "No se puede finalizar mientras haya repuestos sin instalar o devolver")
    previous = order.status
    order.status = target
    order.version += 1
    record_audit(db, user, "WORK_ORDER_STATUS_CHANGED", "work_order", order.id, f"{previous}->{target}: {payload.reason or ''}")
    if target == "PENDING_INSTALLATION":
        customer = db.get(Customer, order.customer_id)
        db.add(
            Notification(
                kind="EXPECTED_PART",
                recipient=customer.email or "" if customer else "",
                status="PENDING",
                idempotency_key=f"expected-part:{order.id}:{order.version}",
            )
        )
    if target == "CANCELLED":
        allocate_queued_work_orders(db)
    db.commit()
    return public_work_order(order)


@router.get("/work-orders/{order_id}/transitions")
def available_transitions(order_id: str, user: CurrentUser, db: Db) -> list[str]:
    order = get_work_order(db, order_id, user)
    return sorted(WORK_ORDER_TRANSITIONS.get(order.status, set()))


@router.post("/work-orders/{order_id}/readmission", response_model=None)
def readmit_work_order(
    order_id: str,
    user: Annotated[User, Depends(require_roles("RECEPTIONIST", "ADMIN"))],
    db: Db,
) -> dict[str, object]:
    order = db.scalar(select(WorkOrder).where(WorkOrder.id == order_id).with_for_update())
    if order is None:
        fail(404, "No se encontró la orden")
    if order.status != "PENDING_INSTALLATION" or not order.expected_part_id:
        fail(409, "La orden no está pendiente de instalación o no tiene un repuesto esperado")
    part = db.scalar(select(Part).where(Part.id == order.expected_part_id).with_for_update())
    if part is None or not part.active or part.physical_stock - part.reserved_stock < 1:
        fail(409, "El repuesto esperado no está disponible")

    part.reserved_stock += 1
    db.add(
        WorkOrderPart(
            work_order_id=order.id,
            part_id=part.id,
            part_name=part.name,
            quantity=1,
            unit_price=part.unit_price,
            status="RESERVED",
        )
    )
    for offset in range(14):
        slot_date = date.today() + timedelta(days=offset)
        if slot_date.weekday() != 6:
            for hour in range(8, 17):
                ensure_slot(db, slot_date, f"{hour:02d}:00")
    slot = db.scalar(
        select(Slot)
        .where(
            Slot.slot_date >= date.today(),
            Slot.booked_count < Slot.capacity,
            Slot.blocked_reason.is_(None),
        )
        .order_by(Slot.slot_date, Slot.start_time)
        .with_for_update()
    )
    order.version += 1
    if slot:
        slot.booked_count += 1
        order.status = "REPAIRING"
        order.queue_position = None
    else:
        queued = db.scalar(
            select(func.count()).select_from(WorkOrder).where(
                WorkOrder.status == "PENDING_INSTALLATION",
                WorkOrder.queue_position.is_not(None),
            )
        ) or 0
        order.queue_position = int(queued) + 1
    record_audit(db, user, "WORK_ORDER_READMITTED", "work_order", order.id)
    db.commit()
    return public_work_order(order)


@router.put("/work-orders/{order_id}/diagnosis", response_model=None)
def save_diagnosis(
    order_id: str,
    payload: DiagnosisRequest,
    user: Annotated[User, Depends(require_roles("MECHANIC"))],
    db: Db,
) -> dict[str, object]:
    order = get_work_order(db, order_id, user)
    if order.status not in {"ASSIGNED", "DIAGNOSING"}:
        fail(409, "El diagnóstico solo se puede registrar en una orden asignada o en diagnóstico")
    order.diagnosis = payload.diagnosis
    if order.status == "ASSIGNED":
        order.status = "DIAGNOSING"
    order.version += 1
    record_audit(db, user, "DIAGNOSIS_SAVED", "work_order", order.id)
    db.commit()
    return public_work_order(order)


@router.post("/work-orders/{order_id}/parts", status_code=201, response_model=None)
def add_work_order_part(
    order_id: str,
    payload: AddPartRequest,
    user: Annotated[User, Depends(require_roles("MECHANIC"))],
    db: Db,
) -> WorkOrderPart:
    order = get_work_order(db, order_id, user)
    if order.status not in {"DIAGNOSING", "REPAIRING"}:
        fail(409, "No se pueden agregar repuestos en el estado actual")
    part = db.scalar(select(Part).where(Part.id == payload.part_id).with_for_update())
    if part is None or not part.active:
        fail(404, "No se encontró el repuesto")
    if part.physical_stock - part.reserved_stock < payload.quantity:
        fail(409, f"Cantidad solicitada supera el stock disponible (Disponible: {part.physical_stock - part.reserved_stock})")
    part.reserved_stock += payload.quantity
    line = WorkOrderPart(
        work_order_id=order.id,
        part_id=part.id,
        part_name=part.name,
        quantity=payload.quantity,
        unit_price=part.unit_price,
    )
    db.add(line)
    record_audit(db, user, "WORK_ORDER_PART_ADDED", "work_order", order.id, part.sku)
    db.commit()
    return line


@router.post("/work-orders/{order_id}/parts/{line_id}/install", response_model=None)
def install_work_order_part(
    order_id: str,
    line_id: str,
    user: Annotated[User, Depends(require_roles("MECHANIC"))],
    db: Db,
) -> WorkOrderPart:
    order = get_work_order(db, order_id, user)
    line = db.get(WorkOrderPart, line_id)
    if line is None or line.work_order_id != order.id or line.status != "RESERVED":
        fail(404, "No se encontró un repuesto reservado en esta orden")
    part = db.scalar(select(Part).where(Part.id == line.part_id).with_for_update())
    if part is None or part.physical_stock < line.quantity or part.reserved_stock < line.quantity:
        fail(409, "El inventario ya no permite instalar este repuesto")
    part.physical_stock -= line.quantity
    part.reserved_stock -= line.quantity
    line.status = "INSTALLED"
    line.installed_at = datetime.now(timezone.utc)
    record_audit(db, user, "WORK_ORDER_PART_INSTALLED", "work_order", order.id, part.sku)
    db.commit()
    return line


@router.post("/work-orders/{order_id}/parts/{line_id}/remove", response_model=None)
def remove_work_order_part(
    order_id: str,
    line_id: str,
    user: Annotated[User, Depends(require_roles("MECHANIC"))],
    db: Db,
) -> WorkOrderPart:
    order = get_work_order(db, order_id, user)
    line = db.get(WorkOrderPart, line_id)
    if line is None or line.work_order_id != order.id or line.status != "RESERVED":
        fail(404, "No se encontró un repuesto reservado en esta orden")
    part = db.get(Part, line.part_id)
    if part:
        part.reserved_stock = max(0, part.reserved_stock - line.quantity)
    line.status = "RETURNED"
    record_audit(db, user, "WORK_ORDER_PART_REMOVED", "work_order", order.id)
    db.commit()
    return line


@router.post("/work-orders/{order_id}/services", status_code=201, response_model=None)
def add_work_order_service(
    order_id: str,
    payload: AddServiceRequest,
    user: Annotated[User, Depends(require_roles("MECHANIC"))],
    db: Db,
) -> WorkOrderService:
    order = get_work_order(db, order_id, user)
    if order.status not in {"DIAGNOSING", "REPAIRING"}:
        fail(409, "No se pueden agregar servicios en el estado actual")
    service = db.get(Service, payload.service_id)
    if service is None or not service.active:
        fail(404, "No se encontró el servicio")
    line = WorkOrderService(work_order_id=order.id, service_name=service.name, applied_price=service.price)
    db.add(line)
    record_audit(db, user, "WORK_ORDER_SERVICE_ADDED", "work_order", order.id, service.code)
    db.commit()
    return line


@router.get("/tracking/{code}")
def public_tracking(code: str, request: Request, db: Db) -> dict[str, object]:
    enforce_tracking_rate_limit(request.client.host if request.client else "unknown")
    normalized_code = normalize_tracking_code(code)
    order = (
        db.scalar(
            select(WorkOrder).where(
                WorkOrder.tracking_code_hash == hash_tracking_code(normalized_code)
            )
        )
        if normalized_code
        else None
    )
    if order is None:
        fail(404, "No encontramos información con ese código. Verifica e intenta de nuevo.")
    vehicle = db.get(Vehicle, order.vehicle_id)
    return {
        "order_number": order.number,
        "vehicle": {"brand": vehicle.brand, "model": vehicle.model} if vehicle else None,
        "status": order.status,
        "updated_at": order.updated_at,
        "expected_part_date": order.expected_part_date if order.status == "PENDING_INSTALLATION" else None,
    }


@router.get("/tracking/{code}/events")
async def tracking_events(code: str, request: Request, db: Db) -> StreamingResponse:
    enforce_tracking_rate_limit(request.client.host if request.client else "unknown")
    normalized_code = normalize_tracking_code(code)
    code_hash = hash_tracking_code(normalized_code) if normalized_code else None
    if code_hash is None or db.scalar(
        select(WorkOrder.id).where(WorkOrder.tracking_code_hash == code_hash)
    ) is None:
        fail(404, "No encontramos información con ese código. Verifica e intenta de nuevo.")

    async def stream():
        previous: str | None = None
        while True:
            with SessionLocal() as stream_db:
                order = stream_db.scalar(
                    select(WorkOrder).where(
                        WorkOrder.tracking_code_hash == code_hash
                    )
                )
                vehicle = stream_db.get(Vehicle, order.vehicle_id) if order else None
                state = (
                    {
                        "order_number": order.number,
                        "status": order.status,
                        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
                        "expected_part_date": (
                            order.expected_part_date.isoformat()
                            if order.status == "PENDING_INSTALLATION" and order.expected_part_date
                            else None
                        ),
                        "vehicle": {"brand": vehicle.brand, "model": vehicle.model} if vehicle else None,
                    }
                    if order
                    else None
                )
            if state is None:
                return
            encoded = json.dumps(state, ensure_ascii=False)
            if encoded != previous:
                yield f"event: work_order.updated\ndata: {encoded}\n\n"
                previous = encoded
            await asyncio.sleep(2)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/users", response_model=None)
def list_users(
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
    role: str | None = None,
    active: bool | None = True,
) -> list[dict[str, object]]:
    statement = select(User).order_by(User.full_name)
    if role:
        statement = statement.where(User.role == role.upper())
    if active is not None:
        statement = statement.where(User.active.is_(active))
    return [public_user(item) for item in db.scalars(statement.limit(200))]


@router.post("/users", status_code=201, response_model=None)
def create_internal_user(
    payload: InternalUserCreate,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> dict[str, object]:
    email = payload.email.lower()
    internal = User(
        full_name=payload.full_name.strip(),
        email=email,
        role=payload.role,
        password_hash=hash_password(payload.temporary_password),
        must_change_password=True,
    )
    db.add(internal)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail(409, "El correo ya se encuentra registrado")
    record_audit(db, user, "INTERNAL_USER_CREATED", "user", internal.id)
    db.commit()
    return public_user(internal)


@router.patch("/users/{user_id}", response_model=None)
def update_user(
    user_id: str,
    payload: UserUpdate,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> dict[str, object]:
    target = db.get(User, user_id)
    if target is None:
        fail(404, "No se encontró el usuario")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("active") is False and target.id == user.id:
        fail(409, "No puede desactivar su propia cuenta")
    if target.id == user.id and changes.get("role", target.role) != "ADMIN":
        fail(409, "No puede quitarse sus propios permisos de administrador")
    if target.role == "CUSTOMER" and "role" in changes:
        fail(409, "No se puede cambiar el rol de una cuenta de cliente")
    if changes.get("email"):
        changes["email"] = changes["email"].lower()
    for key, value in changes.items():
        setattr(target, key, value)
    if changes.get("active") is False:
        for session in db.scalars(
            select(RefreshSession).where(RefreshSession.user_id == target.id)
        ):
            session.revoked = True
    record_audit(db, user, "USER_UPDATED", "user", target.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "El correo ya se encuentra registrado")
    return public_user(target)


@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: str,
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
) -> dict[str, str]:
    target = db.get(User, user_id)
    if target is None:
        fail(404, "No se encontró el usuario")
    if target.id == user.id:
        fail(409, "No puede desactivar su propia cuenta")
    target.active = False
    for session in db.scalars(
        select(RefreshSession).where(RefreshSession.user_id == target.id)
    ):
        session.revoked = True
    record_audit(db, user, "USER_DEACTIVATED", "user", target.id)
    db.commit()
    return {"message": "Usuario desactivado"}


@router.post("/work-orders/{order_id}/settlement")
def settle_work_order(
    order_id: str,
    user: Annotated[User, Depends(require_roles("ADMIN", "RECEPTIONIST"))],
    db: Db,
) -> dict[str, object]:
    order = db.scalar(
        select(WorkOrder)
        .where(WorkOrder.id == order_id)
        .with_for_update()
    )
    if order is None:
        fail(404, "No se encontró la orden")
    if order.status != "FINISHED":
        fail(409, "Solo se puede liquidar una orden finalizada")
    total = sum(
        (line.applied_price for line in db.scalars(select(WorkOrderService).where(WorkOrderService.work_order_id == order.id))),
        Decimal("0"),
    )
    total += sum(
        (
            line.unit_price * line.quantity
            for line in db.scalars(
                select(WorkOrderPart).where(
                    WorkOrderPart.work_order_id == order.id,
                    WorkOrderPart.status == "INSTALLED",
                )
            )
        ),
        Decimal("0"),
    )
    if total <= 0:
        fail(409, "La orden no tiene conceptos cobrables")
    order.status = "PENDING_PAYMENT"
    order.version += 1
    record_audit(db, user, "WORK_ORDER_SETTLED", "work_order", order.id)
    db.commit()
    return {"work_order_id": order.id, "subtotal": total, "vat": (total * Decimal("0.19")).quantize(Decimal("1")), "total": (total * Decimal("1.19")).quantize(Decimal("1"))}


@router.post("/work-orders/{order_id}/payments", status_code=201, response_model=None)
def register_payment(
    order_id: str,
    payload: PaymentRequest,
    user: Annotated[User, Depends(require_roles("ADMIN", "RECEPTIONIST"))],
    db: Db,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=80),
) -> Payment:
    existing = db.scalar(select(Payment).where(Payment.idempotency_key == idempotency_key))
    if existing:
        if (
            existing.work_order_id != order_id
            or existing.amount != payload.amount
            or existing.method != payload.method.upper()
        ):
            fail(409, "La clave de idempotencia ya se utilizó para otro pago")
        return existing
    order = db.scalar(
        select(WorkOrder)
        .where(WorkOrder.id == order_id)
        .with_for_update()
    )
    if order is None:
        fail(404, "No se encontró la orden")
    existing = db.scalar(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    )
    if existing:
        if (
            existing.work_order_id != order_id
            or existing.amount != payload.amount
            or existing.method != payload.method.upper()
        ):
            fail(409, "La clave de idempotencia ya se utilizó para otro pago")
        return existing
    if order.status != "PENDING_PAYMENT":
        fail(409, "La orden debe estar pendiente de pago")
    lines_services = list(db.scalars(select(WorkOrderService).where(WorkOrderService.work_order_id == order.id)))
    lines_parts = list(
        db.scalars(
            select(WorkOrderPart).where(
                WorkOrderPart.work_order_id == order.id,
                WorkOrderPart.status == "INSTALLED",
            )
        )
    )
    subtotal = sum((line.applied_price for line in lines_services), Decimal("0")) + sum(
        (line.unit_price * line.quantity for line in lines_parts), Decimal("0")
    )
    total = (subtotal * Decimal("1.19")).quantize(Decimal("1"))
    if payload.amount != total:
        fail(409, f"El monto no coincide con el total de la orden ({total})")
    number = next_sequence_value(
        db,
        "payment",
        select(Payment.receipt_number),
        "CMP-",
    )
    payment = Payment(
        work_order_id=order.id,
        amount=total,
        method=payload.method.upper(),
        idempotency_key=idempotency_key,
        receipt_number=f"CMP-{number:06d}",
    )
    db.add(payment)
    order.status = "PAID"
    order.version += 1
    record_audit(db, user, "PAYMENT_REGISTERED", "work_order", order.id)
    db.commit()
    return payment


@router.post("/work-orders/{order_id}/delivery")
def deliver_work_order(
    order_id: str,
    user: Annotated[User, Depends(require_roles("ADMIN", "RECEPTIONIST"))],
    db: Db,
) -> dict[str, object]:
    order = db.scalar(
        select(WorkOrder)
        .where(WorkOrder.id == order_id)
        .with_for_update()
    )
    if order is None:
        fail(404, "No se encontró la orden")
    if order.status != "PAID":
        fail(409, "La orden debe estar pagada para registrar la entrega")
    order.status = "DELIVERED"
    order.version += 1
    survey = db.scalar(select(Survey).where(Survey.work_order_id == order.id))
    if survey is None:
        survey = Survey(work_order_id=order.id, token=secrets.token_urlsafe(32))
        db.add(survey)
        db.flush()
    record_audit(db, user, "WORK_ORDER_DELIVERED", "work_order", order.id)
    db.commit()
    return {"status": order.status, "survey_token": survey.token}


@router.get("/surveys/{token}")
def get_survey(token: str, db: Db) -> dict[str, object]:
    survey = db.scalar(select(Survey).where(Survey.token == token))
    if survey is None:
        fail(404, "No se encontró la encuesta")
    order = db.get(WorkOrder, survey.work_order_id)
    if order is None or order.status != "DELIVERED":
        fail(404, "No se encontró la encuesta")
    return {"order_number": order.number, "score": survey.score, "comment": survey.comment}


@router.post("/surveys/{token}")
def submit_survey(token: str, payload: SurveyRequest, db: Db) -> dict[str, object]:
    survey = db.scalar(select(Survey).where(Survey.token == token))
    if survey is None:
        fail(404, "No se encontró la encuesta")
    order = db.get(WorkOrder, survey.work_order_id)
    if order is None or order.status != "DELIVERED":
        fail(404, "No se encontró la encuesta")
    if survey.score is None:
        survey.score = payload.score
        survey.comment = payload.comment
        db.commit()
    return {"score": survey.score, "comment": survey.comment}


@router.get("/me/vehicles/{vehicle_id}/history", response_model=None)
def vehicle_history(
    vehicle_id: str,
    user: Annotated[User, Depends(require_roles("CUSTOMER"))],
    db: Db,
    page: int = Query(default=1, ge=1),
) -> list[WorkOrder]:
    assert_vehicle_access(db, vehicle_id, user)
    return list(
        db.scalars(
            select(WorkOrder)
            .where(WorkOrder.vehicle_id == vehicle_id, WorkOrder.status == "DELIVERED")
            .order_by(WorkOrder.created_at.desc())
            .offset((page - 1) * 20)
            .limit(20)
        )
    )


@router.get("/reports/summary")
def report_summary(
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
    date_from: date = Query(alias="from"),
    date_to: date = Query(alias="to"),
) -> dict[str, object]:
    if date_to < date_from:
        fail(422, "La fecha final no puede ser anterior a la fecha inicial")
    orders = list(
        db.scalars(
            select(WorkOrder).where(
                WorkOrder.created_at >= datetime.combine(date_from, time.min, timezone.utc),
                WorkOrder.created_at < datetime.combine(date_to + timedelta(days=1), time.min, timezone.utc),
            )
        )
    )
    by_status: dict[str, int] = {}
    for order in orders:
        by_status[order.status] = by_status.get(order.status, 0) + 1
    return {"from": date_from, "to": date_to, "orders_total": len(orders), "orders_by_status": by_status}


@router.get("/audit", response_model=None)
def audit_log(
    user: Annotated[User, Depends(require_roles("ADMIN"))],
    db: Db,
    entity: str | None = None,
    entity_id: str | None = None,
) -> list[AuditLog]:
    statement = select(AuditLog).order_by(AuditLog.created_at.desc())
    if entity:
        statement = statement.where(AuditLog.entity == entity)
    if entity_id:
        statement = statement.where(AuditLog.entity_id == entity_id)
    return list(db.scalars(statement.limit(500)))
