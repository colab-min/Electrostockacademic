from collections.abc import Generator
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as app_module
from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.routers import TRACKING_REQUESTS
from app.models import Slot
from app.scheduling import BUSINESS_TIMEZONE
from app.seed import seed_database


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with test_sessions() as db:
        seed_database(
            db,
            Path(__file__).resolve().parents[2] / "fixtures" / "test-data.json",
        )

    def override_get_db():
        with test_sessions() as db:
            yield db

    settings = get_settings().model_copy(
        update={"create_schema": False, "scheduler_enabled": False}
    )
    app.state.test_session_factory = test_sessions
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "SessionLocal", test_sessions)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    del app.state.test_session_factory
    engine.dispose()


def sign_in(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_demo_seed_loads_workshop_queue_and_public_tracking(client: TestClient) -> None:
    admin_token = sign_in(client, "admin@electrostock.test", "Admin2026!")
    orders = client.get("/api/v1/work-orders", headers=admin_token)
    assert orders.status_code == 200
    assert {order["number"] for order in orders.json()} >= {"OT-000001", "OT-000002", "OT-000003"}

    tracking = client.get("/api/v1/tracking/K7M2QX9P4T")
    assert tracking.status_code == 200
    assert tracking.json()["status"] == "REPAIRING"


def test_customer_vehicle_and_technical_record_routes(client: TestClient) -> None:
    headers = sign_in(client, "admin@electrostock.test", "Admin2026!")
    created_customer = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "full_name": "Cliente Nuevo",
            "document_type": "CC",
            "document_number": "1098765432",
            "phone": "3005551234",
            "email": "NUEVO@EXAMPLE.TEST",
            "data_consent": True,
        },
    )
    assert created_customer.status_code == 201
    customer_id = created_customer.json()["id"]
    assert created_customer.json()["email"] == "nuevo@example.test"
    assert client.get(
        "/api/v1/customers",
        headers=headers,
        params={"q": "1098765432"},
    ).json()[0]["id"] == customer_id

    updated_customer = client.patch(
        f"/api/v1/customers/{customer_id}",
        headers=headers,
        json={
            "full_name": "Cliente Editado",
            "document_type": "CE",
            "document_number": "1098765433",
            "phone": "3005554321",
            "email": "ACTUALIZADO@EXAMPLE.TEST",
        },
    )
    assert updated_customer.status_code == 200
    assert updated_customer.json()["full_name"] == "Cliente Editado"
    assert updated_customer.json()["document_number"] == "1098765433"
    assert updated_customer.json()["email"] == "actualizado@example.test"

    created_vehicle = client.post(
        "/api/v1/vehicles",
        headers=headers,
        json={
            "customer_id": customer_id,
            "serial_number": "sc-48-test-new-99",
            "plate": "zzx987",
            "brand": "Electro",
            "model": "Ciudad",
            "year": 2026,
            "battery_capacity_ah": "15.5",
            "cell_type": "Lithium",
            "motor_power_w": 500,
            "controller": "ECU-1",
        },
    )
    assert created_vehicle.status_code == 201
    vehicle_id = created_vehicle.json()["id"]
    assert created_vehicle.json()["serial_number"] == "SC-48-TEST-NEW-99"
    assert created_vehicle.json()["plate"] == "ZZX987"
    duplicate_vehicle = client.post(
        "/api/v1/vehicles",
        headers=headers,
        json={
            "customer_id": customer_id,
            "serial_number": "SC-48-OTHER-99",
            "plate": "ZZX987",
            "brand": "Electro",
            "model": "Ciudad",
        },
    )
    assert duplicate_vehicle.status_code == 409
    assert client.get(
        "/api/v1/vehicles",
        headers=headers,
        params={"q": "ZZX987"},
    ).json()[0]["id"] == vehicle_id
    updated_vehicle = client.patch(
        f"/api/v1/vehicles/{vehicle_id}",
        headers=headers,
        json={"model": "Ciudad Editada", "year": 2025, "plate": "abc456"},
    )
    assert updated_vehicle.status_code == 200
    assert updated_vehicle.json()["model"] == "Ciudad Editada"
    assert updated_vehicle.json()["plate"] == "ABC456"

    note = client.post(
        f"/api/v1/vehicles/{vehicle_id}/notes",
        headers=headers,
        json={"diagnosis": "Se revisó el sistema eléctrico."},
    )
    assert note.status_code == 201
    record = client.get(
        f"/api/v1/vehicles/{vehicle_id}/record",
        headers=headers,
    )
    assert record.status_code == 200
    assert record.json()["notes"][0]["content"] == "Se revisó el sistema eléctrico."
    assert record.json()["work_orders"] == []
    assert client.delete(f"/api/v1/vehicles/{vehicle_id}", headers=headers).status_code == 409
    assert client.delete(f"/api/v1/customers/{customer_id}", headers=headers).status_code == 409

    deletable_customer = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "full_name": "Cliente sin historial",
            "document_type": "CC",
            "document_number": "1098765434",
            "phone": "3005554322",
            "email": None,
            "data_consent": True,
        },
    )
    assert deletable_customer.status_code == 201
    assert client.delete(
        f"/api/v1/customers/{deletable_customer.json()['id']}",
        headers=headers,
    ).status_code == 204
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Cuenta Cliente",
            "email": "cuenta.cliente@example.test",
            "password": "Cuenta2026!x",
            "document_type": "CC",
            "document_number": "1098765435",
            "phone": "3005554323",
            "data_consent": True,
        },
    )
    assert registered.status_code == 201
    registered_customer_id = registered.json()["customer"]["id"]
    updated_account_customer = client.patch(
        f"/api/v1/customers/{registered_customer_id}",
        headers=headers,
        json={
            "full_name": "Cuenta Cliente Editada",
            "email": "cuenta.actualizada@example.test",
        },
    )
    assert updated_account_customer.status_code == 200
    account_login = client.post(
        "/api/v1/auth/login",
        json={"email": "cuenta.actualizada@example.test", "password": "Cuenta2026!x"},
    )
    assert account_login.status_code == 200
    assert account_login.json()["user"]["full_name"] == "Cuenta Cliente Editada"


def test_catalog_and_inventory_management_routes(client: TestClient) -> None:
    admin_headers = sign_in(client, "admin@electrostock.test", "Admin2026!")
    mechanic_headers = sign_in(client, "mecanico1@electrostock.test", "Meca2026!a")
    service = client.post(
        "/api/v1/catalog/services",
        headers=admin_headers,
        json={
            "code": "SVC-TEST",
            "name": "Diagnóstico de prueba",
            "description": "Revisión general",
            "price": "12000",
            "duration_minutes": 60,
        },
    )
    assert service.status_code == 201
    service_id = service.json()["id"]
    duplicate_service = client.post(
        "/api/v1/catalog/services",
        headers=admin_headers,
        json={
            "code": "SVC-TEST",
            "name": "Duplicado",
            "description": "",
            "price": "12000",
            "duration_minutes": 60,
        },
    )
    assert duplicate_service.status_code == 409

    part = client.post(
        "/api/v1/inventory/parts",
        headers=admin_headers,
        json={
            "sku": "PART-TEST",
            "name": "Sensor de prueba",
            "category": "Sensores",
            "voltage": "48V",
            "unit_price": "5000",
            "physical_stock": 3,
            "min_threshold": 1,
        },
    )
    assert part.status_code == 201
    part_id = part.json()["id"]
    assert part.json()["physical_stock"] == 3
    linked = client.put(
        f"/api/v1/catalog/services/{service_id}/parts",
        headers=admin_headers,
        json=[{"part_id": part_id, "quantity": 1}],
    )
    assert linked.status_code == 200
    assert linked.json()["parts"][0]["quantity"] == 1
    assert client.get(
        f"/api/v1/catalog/services/{service_id}/parts",
    ).json()[0]["part"]["sku"] == "PART-TEST"

    updated_service = client.patch(
        f"/api/v1/catalog/services/{service_id}",
        headers=admin_headers,
        json={
            "code": "SVC-TEST",
            "name": "Diagnóstico actualizado",
            "description": "Nueva descripción",
            "price": "13000",
            "duration_minutes": 90,
        },
    )
    assert updated_service.status_code == 200
    assert updated_service.json()["duration_minutes"] == 90
    assert client.patch(
        f"/api/v1/catalog/services/{service_id}",
        headers=admin_headers,
        json={"active": False},
    ).json()["active"] is False
    assert any(
        item["id"] == service_id
        for item in client.get(
            "/api/v1/catalog/services",
            params={"active": False},
        ).json()
    )
    assert client.patch(
        f"/api/v1/catalog/services/{service_id}",
        headers=admin_headers,
        json={"active": True},
    ).json()["active"] is True
    updated_part = client.patch(
        f"/api/v1/inventory/parts/{part_id}",
        headers=admin_headers,
        json={"name": "Sensor actualizado"},
    )
    assert updated_part.status_code == 200
    assert client.patch(
        f"/api/v1/inventory/parts/{part_id}",
        headers=admin_headers,
        json={"sku": "PART-TEST-EDITED"},
    ).json()["sku"] == "PART-TEST-EDITED"
    threshold = client.patch(
        f"/api/v1/inventory/parts/{part_id}/threshold",
        headers=admin_headers,
        params={"min_threshold": 3},
    )
    assert threshold.status_code == 200
    assert threshold.json()["min_threshold"] == 3
    stock = client.get(
        "/api/v1/inventory/parts",
        headers=admin_headers,
        params={"category": "Sensores", "alerts_only": True},
    ).json()
    assert [item["id"] for item in stock] == [part_id]

    search = client.get(
        "/api/v1/inventory/parts/search",
        headers=mechanic_headers,
        params={"q": "Sensor actualizado"},
    )
    assert search.status_code == 200
    assert search.json()[0]["id"] == part_id
    movement = client.post(
        "/api/v1/inventory/movements",
        headers=admin_headers,
        json={
            "part_id": part_id,
            "type": "IN",
            "quantity": 2,
            "reason": "Ingreso de prueba",
        },
    )
    assert movement.status_code == 201
    assert movement.json()["quantity"] == 2
    written_off = client.post(
        "/api/v1/inventory/movements",
        headers=admin_headers,
        json={
            "part_id": part_id,
            "type": "WRITE_OFF",
            "quantity": 1,
            "reason": "Baja de prueba",
        },
    )
    assert written_off.status_code == 201

    assert client.post(
        f"/api/v1/inventory/parts/{part_id}/deactivate",
        headers=admin_headers,
    ).status_code == 200
    inactive_parts = client.get(
        "/api/v1/inventory/parts",
        headers=admin_headers,
        params={"active": False},
    ).json()
    assert any(item["id"] == part_id for item in inactive_parts)
    assert client.patch(
        f"/api/v1/inventory/parts/{part_id}",
        headers=admin_headers,
        json={"active": True},
    ).json()["active"] is True
    assert client.patch(
        f"/api/v1/inventory/parts/{part_id}",
        headers=admin_headers,
        json={"active": False},
    ).json()["active"] is False
    assert any(
        item["id"] == part_id
        for item in client.get(
            "/api/v1/inventory/parts",
            headers=admin_headers,
            params={"active": False},
        ).json()
    )
    assert all(
        item["id"] != part_id
        for item in client.get("/api/v1/inventory/parts", headers=admin_headers).json()
    )
    assert client.post(
        f"/api/v1/catalog/services/{service_id}/deactivate",
        headers=admin_headers,
    ).status_code == 200
    inactive = client.get("/api/v1/catalog/services", params={"active": "false"})
    assert any(item["id"] == service_id for item in inactive.json())


def test_user_management_reports_and_audit_routes(client: TestClient) -> None:
    headers = sign_in(client, "admin@electrostock.test", "Admin2026!")
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "full_name": "Recepción temporal",
            "email": "NUEVA-RECEPCION@EXAMPLE.TEST",
            "role": "RECEPTIONIST",
            "temporary_password": "Temporal2026!",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert created.json()["email"] == "nueva-recepcion@example.test"
    updated = client.patch(
        f"/api/v1/users/{user_id}",
        headers=headers,
        json={
            "full_name": "Recepción actualizada",
            "email": "ACTUALIZADA-RECEPCION@EXAMPLE.TEST",
            "role": "MECHANIC",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["email"] == "actualizada-recepcion@example.test"
    assert updated.json()["role"] == "MECHANIC"

    users = client.get(
        "/api/v1/users",
        headers=headers,
        params={"role": "MECHANIC", "active": True},
    ).json()
    assert any(item["id"] == user_id for item in users)
    admin = next(
        item
        for item in client.get("/api/v1/users", headers=headers).json()
        if item["email"] == "admin@electrostock.test"
    )
    self_deactivate = client.post(
        f"/api/v1/users/{admin['id']}/deactivate",
        headers=headers,
    )
    assert self_deactivate.status_code == 409
    deactivated = client.post(
        f"/api/v1/users/{user_id}/deactivate",
        headers=headers,
    )
    assert deactivated.status_code == 200
    assert any(
        item["id"] == user_id
        for item in client.get(
            "/api/v1/users",
            headers=headers,
            params={"active": False},
        ).json()
    )
    reactivated = client.patch(
        f"/api/v1/users/{user_id}",
        headers=headers,
        json={"active": True},
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["active"] is True

    report = client.get(
        "/api/v1/reports/summary",
        headers=headers,
        params={"from": "2000-01-01", "to": "2100-01-01"},
    )
    assert report.status_code == 200
    assert report.json()["orders_total"] > 0
    assert sum(report.json()["orders_by_status"].values()) == report.json()["orders_total"]
    invalid_report = client.get(
        "/api/v1/reports/summary",
        headers=headers,
        params={"from": "2026-11-13", "to": "2026-11-12"},
    )
    assert invalid_report.status_code == 422
    audit = client.get(
        "/api/v1/audit",
        headers=headers,
        params={"entity": "user", "entity_id": user_id},
    )
    assert audit.status_code == 200
    assert {item["action"] for item in audit.json()} >= {
        "INTERNAL_USER_CREATED",
        "USER_UPDATED",
        "USER_DEACTIVATED",
    }


def test_login_role_guards_and_no_password_leak(client: TestClient) -> None:
    customer_token = sign_in(client, "cliente1@electrostock.test", "Cliente2026!")
    denied = client.get("/api/v1/users", headers=customer_token)
    assert denied.status_code == 403

    admin_token = sign_in(client, "admin@electrostock.test", "Admin2026!")
    users = client.get("/api/v1/users", headers=admin_token)
    assert users.status_code == 200
    assert users.json()
    assert "password_hash" not in users.json()[0]


def test_login_locks_account_after_five_failed_attempts(client: TestClient) -> None:
    credentials = {
        "email": "admin@electrostock.test",
        "password": "Incorrecta2026!",
    }
    for _ in range(5):
        response = client.post("/api/v1/auth/login", json=credentials)
        assert response.status_code == 401

    locked = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@electrostock.test", "password": "Admin2026!"},
    )
    assert locked.status_code == 401


def test_temporary_password_limits_access_until_changed(client: TestClient) -> None:
    admin_headers = sign_in(client, "admin@electrostock.test", "Admin2026!")
    created = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "full_name": "Usuario Temporal",
            "email": "temporal@electrostock.test",
            "role": "RECEPTIONIST",
            "temporary_password": "Temporal2026!",
        },
    )
    assert created.status_code == 201
    assert created.json()["must_change_password"] is True

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "temporal@electrostock.test",
            "password": "Temporal2026!",
        },
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.get("/api/v1/inventory/parts", headers=headers).status_code == 403
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "Temporal2026!",
            "new_password": "NuevaClave2026!",
        },
    )
    assert changed.status_code == 200
    assert client.get("/api/v1/inventory/parts", headers=headers).status_code == 200


def test_customer_books_confirms_and_cancels_with_stock_release(client: TestClient) -> None:
    customer_token = sign_in(client, "cliente1@electrostock.test", "Cliente2026!")
    vehicles = client.get("/api/v1/vehicles/mine", headers=customer_token)
    assert vehicles.status_code == 200
    vehicle_id = vehicles.json()[0]["id"]

    service = next(
        item
        for item in client.get("/api/v1/catalog/services").json()
        if item["code"] == "CAMB-BAT-48"
    )
    start = client.get("/api/v1/scheduling/availability").json()
    available_slot = next(item for item in start if item["available"] > 0 and not item["blocked"])
    booked = client.post(
        "/api/v1/scheduling/appointments",
        headers=customer_token,
        json={"vehicle_id": vehicle_id, "service_id": service["id"], "slot_id": available_slot["id"]},
    )
    assert booked.status_code == 201
    appointment_id = booked.json()["id"]

    admin_token = sign_in(client, "admin@electrostock.test", "Admin2026!")
    inventory = client.get("/api/v1/inventory/parts", headers=admin_token).json()
    battery = next(item for item in inventory if item["sku"] == "BAT-48-15")
    assert battery["reserved_stock"] == 1

    confirmed = client.post(
        f"/api/v1/scheduling/appointments/{appointment_id}/confirm",
        headers=customer_token,
    )
    assert confirmed.status_code == 200
    cancelled = client.post(
        f"/api/v1/scheduling/appointments/{appointment_id}/cancel",
        headers=customer_token,
        json={"reason": "Cambio de planes"},
    )
    assert cancelled.status_code == 200
    inventory_after = client.get("/api/v1/inventory/parts", headers=admin_token).json()
    battery_after = next(item for item in inventory_after if item["sku"] == "BAT-48-15")
    assert battery_after["reserved_stock"] == 0


def test_appointment_keeps_original_part_reservation_after_service_parts_change(
    client: TestClient,
) -> None:
    admin_headers = sign_in(client, "admin@electrostock.test", "Admin2026!")
    customer_headers = sign_in(client, "cliente1@electrostock.test", "Cliente2026!")
    service = next(
        service
        for service in client.get("/api/v1/catalog/services").json()
        if service["code"] == "CAMB-BAT-48"
    )
    inventory = client.get(
        "/api/v1/inventory/parts",
        headers=admin_headers,
    ).json()
    battery = next(part for part in inventory if part["sku"] == "BAT-48-15")
    brake = next(part for part in inventory if part["sku"] == "BRK-01")

    updated = client.put(
        f"/api/v1/catalog/services/{service['id']}/parts",
        headers=admin_headers,
        json=[{"part_id": battery["id"], "quantity": 1}],
    )
    assert updated.status_code == 200
    duplicate = client.put(
        f"/api/v1/catalog/services/{service['id']}/parts",
        headers=admin_headers,
        json=[
            {"part_id": battery["id"], "quantity": 1},
            {"part_id": battery["id"], "quantity": 2},
        ],
    )
    assert duplicate.status_code == 422

    vehicle = next(
        item
        for item in client.get(
            "/api/v1/vehicles/mine",
            headers=customer_headers,
        ).json()
        if item["serial_number"] == "SC-48-0001"
    )
    available = client.get(
        "/api/v1/scheduling/availability",
        params={
            "from": (date.today() + timedelta(days=1)).isoformat(),
            "days": 7,
            "service_id": service["id"],
        },
    ).json()
    booking = client.post(
        "/api/v1/scheduling/appointments",
        headers=customer_headers,
        json={
            "vehicle_id": vehicle["id"],
            "service_id": service["id"],
            "slot_id": available[0]["id"],
        },
    )
    assert booking.status_code == 201
    assert next(
        part
        for part in client.get("/api/v1/inventory/parts", headers=admin_headers).json()
        if part["id"] == battery["id"]
    )["reserved_stock"] == 1

    changed = client.put(
        f"/api/v1/catalog/services/{service['id']}/parts",
        headers=admin_headers,
        json=[{"part_id": brake["id"], "quantity": 2}],
    )
    assert changed.status_code == 200
    assert changed.json()["preserved_appointment_reservations"] == 1
    cancelled = client.post(
        f"/api/v1/scheduling/appointments/{booking.json()['id']}/cancel",
        headers=customer_headers,
        json={"reason": "Verificación de reserva original"},
    )
    assert cancelled.status_code == 200

    final_inventory = client.get(
        "/api/v1/inventory/parts",
        headers=admin_headers,
    ).json()
    assert next(part for part in final_inventory if part["id"] == battery["id"])[
        "reserved_stock"
    ] == 0
    assert next(part for part in final_inventory if part["id"] == brake["id"])[
        "reserved_stock"
    ] == 0


def test_appointment_cannot_be_rescheduled_within_one_hour(client: TestClient) -> None:
    customer_headers = sign_in(client, "cliente1@electrostock.test", "Cliente2026!")
    vehicle = client.get(
        "/api/v1/vehicles/mine",
        headers=customer_headers,
    ).json()[0]
    service = client.get("/api/v1/catalog/services").json()[0]
    available = client.get(
        "/api/v1/scheduling/availability",
        params={
            "from": (date.today() + timedelta(days=1)).isoformat(),
            "days": 7,
            "service_id": service["id"],
        },
    ).json()
    booking = client.post(
        "/api/v1/scheduling/appointments",
        headers=customer_headers,
        json={
            "vehicle_id": vehicle["id"],
            "service_id": service["id"],
            "slot_id": available[0]["id"],
        },
    )
    assert booking.status_code == 201
    with client.app.state.test_session_factory() as db:
        start_slot = db.get(Slot, booking.json()["slot_id"])
        assert start_slot is not None
        start_slot.slot_date = datetime.now(BUSINESS_TIMEZONE).date() - timedelta(days=1)
        db.commit()

    response = client.post(
        f"/api/v1/scheduling/appointments/{booking.json()['id']}/reschedule",
        headers=customer_headers,
        json={"slot_id": available[1]["id"]},
    )
    assert response.status_code == 409
    assert "una hora" in response.json()["detail"]


def test_long_appointment_reserves_consecutive_slots_and_releases_them(
    client: TestClient,
) -> None:
    customer_token = sign_in(client, "cliente1@electrostock.test", "Cliente2026!")
    vehicle = next(
        vehicle
        for vehicle in client.get(
            "/api/v1/vehicles/mine",
            headers=customer_token,
        ).json()
        if vehicle["serial_number"] == "SC-48-0001"
    )
    service = next(
        service
        for service in client.get("/api/v1/catalog/services").json()
        if service["code"] == "MANT-PREV"
    )
    available = client.get(
        "/api/v1/scheduling/availability",
        params={"from": (date.today() + timedelta(days=1)).isoformat(), "days": 7, "service_id": service["id"]},
    ).json()
    starts = {(item["date"], item["start_time"]) for item in available}
    assert any(start_time == "16:00" for _, start_time in starts)
    assert not any(start_time == "17:00" for _, start_time in starts)

    start = next(item for item in available if item["start_time"] == "16:00")
    booked = client.post(
        "/api/v1/scheduling/appointments",
        headers=customer_token,
        json={
            "vehicle_id": vehicle["id"],
            "service_id": service["id"],
            "slot_id": start["id"],
        },
    )
    assert booked.status_code == 201

    admin_token = sign_in(client, "admin@electrostock.test", "Admin2026!")
    occupancy = client.get(
        "/api/v1/scheduling/occupancy",
        headers=admin_token,
        params={"month": start["date"][:7]},
    ).json()
    booked_slots = {
        row["start_time"]: row["booked_count"]
        for row in occupancy
        if row["date"] == start["date"]
    }
    assert booked_slots["16:00"] == 1
    assert booked_slots["17:00"] == 1

    next_day_start = next(
        item
        for item in available
        if item["date"] != start["date"] and item["start_time"] == "15:00"
    )
    rescheduled = client.post(
        f"/api/v1/scheduling/appointments/{booked.json()['id']}/reschedule",
        headers=customer_token,
        json={"slot_id": next_day_start["id"]},
    )
    assert rescheduled.status_code == 200
    occupancy = client.get(
        "/api/v1/scheduling/occupancy",
        headers=admin_token,
        params={"month": next_day_start["date"][:7]},
    ).json()
    rescheduled_slot_counts = {
        row["start_time"]: row["booked_count"]
        for row in occupancy
        if row["date"] == next_day_start["date"]
    }
    assert rescheduled_slot_counts["15:00"] == 1
    assert rescheduled_slot_counts["16:00"] == 1

    cancelled = client.post(
        f"/api/v1/scheduling/appointments/{booked.json()['id']}/cancel",
        headers=customer_token,
        json={"reason": "Prueba de liberación"},
    )
    assert cancelled.status_code == 200
    occupancy = client.get(
        "/api/v1/scheduling/occupancy",
        headers=admin_token,
        params={"month": next_day_start["date"][:7]},
    ).json()
    released_slot_counts = {
        row["start_time"]: row["booked_count"]
        for row in occupancy
        if row["date"] == next_day_start["date"]
    }
    assert released_slot_counts["15:00"] == 0
    assert released_slot_counts["16:00"] == 0


def test_appointment_parts_transfer_to_work_order_and_release_slot(client: TestClient) -> None:
    customer_token = sign_in(client, "cliente1@electrostock.test", "Cliente2026!")
    admin_token = sign_in(client, "admin@electrostock.test", "Admin2026!")
    receptionist_token = sign_in(client, "recepcion@electrostock.test", "Recep2026!")
    vehicle = next(
        vehicle for vehicle in client.get("/api/v1/vehicles/mine", headers=customer_token).json()
        if vehicle["serial_number"] == "SC-48-0001"
    )
    service = next(
        service for service in client.get("/api/v1/catalog/services").json()
        if service["code"] == "CAMB-BAT-48"
    )
    available_slot = next(
        slot for slot in client.get("/api/v1/scheduling/availability").json()
        if slot["available"] > 0 and not slot["blocked"]
    )
    booking = client.post(
        "/api/v1/scheduling/appointments",
        headers=customer_token,
        json={
            "vehicle_id": vehicle["id"],
            "service_id": service["id"],
            "slot_id": available_slot["id"],
        },
    )
    assert booking.status_code == 201
    active_appointment_walk_in = client.post(
        "/api/v1/scheduling/walk-ins",
        headers={
            **receptionist_token,
            "Idempotency-Key": "active-appointment-walk-in-01",
        },
        json={
            "vehicle_id": vehicle["id"],
            "service_id": service["id"],
            "fault_type": "F02",
            "fault_description": "Ingreso no permitido",
        },
    )
    assert active_appointment_walk_in.status_code == 409
    duplicate_order = client.post(
        "/api/v1/work-orders",
        headers=receptionist_token,
        json={"vehicle_id": vehicle["id"], "fault_description": "Orden no permitida"},
    )
    assert duplicate_order.status_code == 409
    inventory = client.get("/api/v1/inventory/parts", headers=admin_token).json()
    battery = next(part for part in inventory if part["sku"] == "BAT-48-15")
    assert battery["reserved_stock"] == 1

    confirmed = client.post(
        f"/api/v1/scheduling/appointments/{booking.json()['id']}/confirm",
        headers=customer_token,
    )
    assert confirmed.status_code == 200
    created = client.post(
        "/api/v1/work-orders",
        headers=receptionist_token,
        json={"appointment_code": booking.json()["code"], "fault_description": "Cambio de batería"},
    )
    assert created.status_code == 201
    detail = client.get(
        f"/api/v1/work-orders/{created.json()['id']}",
        headers=admin_token,
    ).json()
    assert detail["services"][0]["service_name"] == "Cambio de batería 48V"
    assert detail["parts"][0]["part_name"] == "Batería litio 48V 15Ah"
    assert detail["parts"][0]["status"] == "RESERVED"

    appointment_after = next(
        appointment
        for appointment in client.get(
            "/api/v1/scheduling/appointments/mine",
            headers=customer_token,
        ).json()
        if appointment["id"] == booking.json()["id"]
    )
    occupancy = client.get(
        f"/api/v1/scheduling/occupancy?month={available_slot['date'][:7]}",
        headers=admin_token,
    ).json()
    slot_after = next(slot for slot in occupancy if slot["id"] == available_slot["id"])
    assert appointment_after["status"] == "ATTENDED"
    assert slot_after["booked_count"] == 0
    inventory_after = client.get("/api/v1/inventory/parts", headers=admin_token).json()
    battery_after = next(part for part in inventory_after if part["sku"] == "BAT-48-15")
    assert battery_after["reserved_stock"] == 1
    duplicate = client.post(
        "/api/v1/work-orders",
        headers=receptionist_token,
        json={"vehicle_id": vehicle["id"], "fault_description": "Segunda orden"},
    )
    assert duplicate.status_code == 409


def test_work_order_repair_payment_delivery_and_survey_flow(client: TestClient) -> None:
    admin_headers = sign_in(client, "admin@electrostock.test", "Admin2026!")
    receptionist_headers = sign_in(client, "recepcion@electrostock.test", "Recep2026!")
    customer = client.post(
        "/api/v1/customers",
        headers=admin_headers,
        json={
            "full_name": "Cliente de ciclo completo",
            "document_type": "CC",
            "document_number": "1098765500",
            "phone": "3005555500",
            "email": "ciclo@example.test",
            "data_consent": True,
        },
    )
    assert customer.status_code == 201
    vehicle = client.post(
        "/api/v1/vehicles",
        headers=admin_headers,
        json={
            "customer_id": customer.json()["id"],
            "serial_number": "SC-48-LIFECYCLE-01",
            "brand": "Electro",
            "model": "Ciudad",
        },
    )
    assert vehicle.status_code == 201
    services = client.get("/api/v1/catalog/services").json()
    diagnosis_service = next(item for item in services if item["code"] == "DIAG-GEN")
    repair_service = next(item for item in services if item["code"] == "MANT-PREV")
    created = client.post(
        "/api/v1/work-orders",
        headers=receptionist_headers,
        json={
            "vehicle_id": vehicle.json()["id"],
            "service_id": diagnosis_service["id"],
            "fault_type": "F03",
            "fault_description": "Revisión de sistema eléctrico",
        },
    )
    assert created.status_code == 201
    order_id = created.json()["id"]
    mechanics = client.get(
        "/api/v1/users",
        headers=admin_headers,
        params={"role": "MECHANIC", "active": True},
    ).json()
    mechanic = next(
        item for item in mechanics if item["email"] == "mecanico1@electrostock.test"
    )
    assigned = client.patch(
        f"/api/v1/work-orders/{order_id}/assignment",
        headers=admin_headers,
        json={"mechanic_id": mechanic["id"], "version": created.json()["version"]},
    )
    assert assigned.status_code == 200
    mechanic_headers = sign_in(client, "mecanico1@electrostock.test", "Meca2026!a")
    diagnosis = client.put(
        f"/api/v1/work-orders/{order_id}/diagnosis",
        headers=mechanic_headers,
        json={"diagnosis": "Controlador y conexiones en buen estado."},
    )
    assert diagnosis.status_code == 200
    assert diagnosis.json()["status"] == "DIAGNOSING"

    part = next(
        item
        for item in client.get(
            "/api/v1/inventory/parts",
            headers=admin_headers,
        ).json()
        if item["available_stock"] >= 2
    )
    installed = client.post(
        f"/api/v1/work-orders/{order_id}/parts",
        headers=mechanic_headers,
        json={"part_id": part["id"], "quantity": 1},
    )
    returned = client.post(
        f"/api/v1/work-orders/{order_id}/parts",
        headers=mechanic_headers,
        json={"part_id": part["id"], "quantity": 1},
    )
    assert installed.status_code == returned.status_code == 201
    added_service = client.post(
        f"/api/v1/work-orders/{order_id}/services",
        headers=mechanic_headers,
        json={"service_id": repair_service["id"]},
    )
    assert added_service.status_code == 201
    install_result = client.post(
        f"/api/v1/work-orders/{order_id}/parts/{installed.json()['id']}/install",
        headers=mechanic_headers,
    )
    remove_result = client.post(
        f"/api/v1/work-orders/{order_id}/parts/{returned.json()['id']}/remove",
        headers=mechanic_headers,
    )
    assert install_result.status_code == remove_result.status_code == 200
    assert install_result.json()["status"] == "INSTALLED"
    assert remove_result.json()["status"] == "RETURNED"
    repairing = client.patch(
        f"/api/v1/work-orders/{order_id}/status",
        headers=mechanic_headers,
        json={"status": "REPAIRING"},
    )
    assert repairing.status_code == 200
    assert client.get(
        f"/api/v1/work-orders/{order_id}/transitions",
        headers=mechanic_headers,
    ).json() == ["CANCELLED", "FINISHED", "WAITING_PARTS"]
    finished = client.patch(
        f"/api/v1/work-orders/{order_id}/status",
        headers=mechanic_headers,
        json={"status": "FINISHED"},
    )
    assert finished.status_code == 200

    settlement = client.post(
        f"/api/v1/work-orders/{order_id}/settlement",
        headers=receptionist_headers,
    )
    assert settlement.status_code == 200
    payment_headers = {
        **receptionist_headers,
        "Idempotency-Key": "payment-flow-test-0001",
    }
    payment_payload = {
        "amount": str(settlement.json()["total"]),
        "method": "card",
    }
    payment = client.post(
        f"/api/v1/work-orders/{order_id}/payments",
        headers=payment_headers,
        json=payment_payload,
    )
    assert payment.status_code == 201
    replay = client.post(
        f"/api/v1/work-orders/{order_id}/payments",
        headers=payment_headers,
        json=payment_payload,
    )
    assert replay.status_code == 201
    assert replay.json()["receipt_number"] == payment.json()["receipt_number"]

    delivered = client.post(
        f"/api/v1/work-orders/{order_id}/delivery",
        headers=receptionist_headers,
    )
    assert delivered.status_code == 200
    token = delivered.json()["survey_token"]
    survey = client.get(f"/api/v1/surveys/{token}")
    assert survey.status_code == 200
    submitted = client.post(
        f"/api/v1/surveys/{token}",
        json={"score": 5, "comment": "Atención excelente"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["score"] == 5
    assert client.get(f"/api/v1/surveys/{token}").json()["comment"] == "Atención excelente"


def test_work_order_assignment_and_mechanic_ownership(client: TestClient) -> None:
    admin_token = sign_in(client, "admin@electrostock.test", "Admin2026!")
    customer = client.post(
        "/api/v1/customers",
        headers=admin_token,
        json={
            "full_name": "Cliente de asignación",
            "document_type": "CC",
            "document_number": "1098765510",
            "phone": "3005555510",
            "email": "asignacion@example.test",
            "data_consent": True,
        },
    )
    vehicle = client.post(
        "/api/v1/vehicles",
        headers=admin_token,
        json={
            "customer_id": customer.json()["id"],
            "serial_number": "SC-48-ASSIGN-01",
            "brand": "Electro",
            "model": "Ciudad",
        },
    )
    created = client.post(
        "/api/v1/work-orders",
        headers=admin_token,
        json={"vehicle_id": vehicle.json()["id"], "fault_description": "Revisión general"},
    )
    assert created.status_code == 201
    assert created.json()["number"] == "OT-000004"
    order = created.json()

    mechanics = client.get("/api/v1/users?role=MECHANIC&active=true", headers=admin_token).json()
    mechanic = next(user for user in mechanics if user["email"] == "mecanico1@electrostock.test")
    assigned = client.patch(
        f"/api/v1/work-orders/{order['id']}/assignment",
        headers=admin_token,
        json={"mechanic_id": mechanic["id"], "version": order["version"]},
    )
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "ASSIGNED"

    other_mechanic = sign_in(client, "mecanico2@electrostock.test", "Meca2026!b")
    denied = client.patch(
        f"/api/v1/work-orders/{order['id']}/status",
        headers=other_mechanic,
        json={"status": "DIAGNOSING"},
    )
    assert denied.status_code == 403

    mechanic_token = sign_in(client, "mecanico1@electrostock.test", "Meca2026!a")
    diagnosing = client.patch(
        f"/api/v1/work-orders/{order['id']}/status",
        headers=mechanic_token,
        json={"status": "DIAGNOSING"},
    )
    assert diagnosing.status_code == 200
    diagnosis = client.put(
        f"/api/v1/work-orders/{order['id']}/diagnosis",
        headers=mechanic_token,
        json={"diagnosis": "Batería con capacidad reducida"},
    )
    assert diagnosis.status_code == 200
    assert diagnosis.json()["diagnosis"] == "Batería con capacidad reducida"


def test_registration_requires_consent_and_valid_password(client: TestClient) -> None:
    data = {
        "full_name": "Nueva Persona",
        "email": "nueva.persona@electrostock.test",
        "password": "Valida2026!x",
        "document_type": "CC",
        "document_number": "1234567890",
        "phone": "3005551212",
        "data_consent": False,
    }
    without_consent = client.post("/api/v1/auth/register", json=data)
    assert without_consent.status_code == 422

    data["data_consent"] = True
    response = client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 201
    assert response.json()["customer"]["data_consent_version"] == "v1"
    assert "password_hash" not in response.json()["user"]


def test_refresh_cookie_is_rotated_and_old_token_is_revoked(client: TestClient) -> None:
    origin = get_settings().cors_origins.split(",")[0].strip()
    headers = {"Origin": origin}
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@electrostock.test", "password": "Admin2026!"},
    )
    old_token = login.cookies.get("electrostock_refresh")
    assert old_token
    assert "samesite=strict" in login.headers["set-cookie"].lower()

    refreshed = client.post("/api/v1/auth/refresh", headers=headers)
    new_token = refreshed.cookies.get("electrostock_refresh")
    assert refreshed.status_code == 200
    assert new_token and new_token != old_token
    assert "samesite=strict" in refreshed.headers["set-cookie"].lower()

    replay = client.post(
        "/api/v1/auth/refresh",
        cookies={"electrostock_refresh": old_token},
        headers=headers,
    )
    assert replay.status_code == 401
    family_revoked = client.post(
        "/api/v1/auth/refresh",
        cookies={"electrostock_refresh": new_token},
        headers=headers,
    )
    assert family_revoked.status_code == 401


def test_refresh_and_logout_reject_untrusted_origins(client: TestClient) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@electrostock.test", "password": "Admin2026!"},
    )
    assert login.status_code == 200
    refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "https://untrusted.example"},
    )
    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://untrusted.example"},
    )
    assert refresh.status_code == 403
    assert logout.status_code == 403


def test_public_tracking_rate_limit(client: TestClient) -> None:
    TRACKING_REQUESTS.clear()
    for _ in range(30):
        response = client.get("/api/v1/tracking/invalid-code")
        assert response.status_code == 404
    limited = client.get("/api/v1/tracking/invalid-code")
    assert limited.status_code == 429


def test_tracking_code_is_returned_once_and_looked_up_by_hash(client: TestClient) -> None:
    TRACKING_REQUESTS.clear()
    admin_token = sign_in(client, "admin@electrostock.test", "Admin2026!")
    customer = client.post(
        "/api/v1/customers",
        headers=admin_token,
        json={
            "full_name": "Cliente de seguimiento",
            "document_type": "CC",
            "document_number": "1098765520",
            "phone": "3005555520",
            "email": "seguimiento@example.test",
            "data_consent": True,
        },
    )
    vehicle = client.post(
        "/api/v1/vehicles",
        headers=admin_token,
        json={
            "customer_id": customer.json()["id"],
            "serial_number": "SC-48-TRACK-01",
            "brand": "Electro",
            "model": "Ciudad",
        },
    )
    service = next(
        item
        for item in client.get("/api/v1/catalog/services").json()
        if item["code"] == "DIAG-GEN"
    )

    created = client.post(
        "/api/v1/work-orders",
        headers=admin_token,
        json={
            "vehicle_id": vehicle.json()["id"],
            "service_id": service["id"],
            "fault_description": "Verificación del código de seguimiento",
        },
    )

    assert created.status_code == 201
    tracking_code = created.json()["tracking_code"]
    assert len(tracking_code) == 10
    assert tracking_code.isalnum()
    assert "tracking_code_hash" not in created.json()

    listed = next(
        order
        for order in client.get("/api/v1/work-orders", headers=admin_token).json()
        if order["id"] == created.json()["id"]
    )
    assert "tracking_code" not in listed
    assert "tracking_code_hash" not in listed
    assert client.get(f"/api/v1/tracking/{tracking_code}").status_code == 200
    assert client.get(f"/api/v1/tracking/{tracking_code.lower()}").status_code == 200

    missing = client.get("/api/v1/tracking/0000000000")
    malformed = client.get("/api/v1/tracking/invalid-code")
    assert missing.status_code == malformed.status_code == 404
    assert missing.json() == malformed.json()


def test_walk_in_requires_service_and_records_price_and_queue(client: TestClient) -> None:
    receptionist_token = sign_in(client, "recepcion@electrostock.test", "Recep2026!")
    walk_in_headers = {
        **receptionist_token,
        "Idempotency-Key": "walk-in-test-request-0001",
    }
    customers = client.get("/api/v1/customers", headers=receptionist_token).json()
    customer = next(
        customer for customer in customers
        if customer["document_number"] == "1045678901"
    )
    vehicle = client.post(
        "/api/v1/vehicles",
        headers=receptionist_token,
        json={
            "customer_id": customer["id"],
            "serial_number": "WALK-TEST-01",
            "brand": "Electro",
            "model": "Demo walk-in",
        },
    )
    assert vehicle.status_code == 201
    without_service = client.post(
        "/api/v1/scheduling/walk-ins",
        headers=walk_in_headers,
        json={"vehicle_id": vehicle.json()["id"], "fault_description": "Frenos sin respuesta"},
    )
    assert without_service.status_code == 422

    service = next(
        service for service in client.get("/api/v1/catalog/services").json()
        if service["code"] == "MANT-PREV"
    )
    created = client.post(
        "/api/v1/scheduling/walk-ins",
        headers=walk_in_headers,
        json={
            "vehicle_id": vehicle.json()["id"],
            "service_id": service["id"],
            "fault_description": "Frenos sin respuesta",
            "fault_type": "F02",
        },
    )
    assert created.status_code == 201
    detail = client.get(
        f"/api/v1/work-orders/{created.json()['id']}",
        headers=receptionist_token,
    ).json()
    assert float(detail["services"][0]["applied_price"]) == 45000
    assert created.json()["queue_position"] is None
    assert created.json()["scheduled_start_at"] is not None
    replay = client.post(
        "/api/v1/scheduling/walk-ins",
        headers=walk_in_headers,
        json={
            "vehicle_id": vehicle.json()["id"],
            "service_id": service["id"],
            "fault_description": "Frenos sin respuesta",
            "fault_type": "F02",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == created.json()["id"]
    assert "tracking_code" not in replay.json()
    changed_request = client.post(
        "/api/v1/scheduling/walk-ins",
        headers=walk_in_headers,
        json={
            "vehicle_id": vehicle.json()["id"],
            "service_id": service["id"],
            "fault_description": "Solicitud distinta",
            "fault_type": "F02",
        },
    )
    assert changed_request.status_code == 409
