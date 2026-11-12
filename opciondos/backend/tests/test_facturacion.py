"""Facturación: liquidar, cobrar, entregar (HU-13), ticket (HU-17) y encuesta (HU-16)."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.modulos.ordenes.modelos import WorkOrder

RECEPCION = {"email": "recepcion@electrostock.test", "password": "Recep2026!"}


def auth(c: TestClient) -> dict:
    r = c.post("/api/auth/login", json=RECEPCION)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def orden_id(numero: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(WorkOrder.id).where(WorkOrder.number == numero))  # type: ignore[return-value]


def test_cobro_exacto_comprobante_y_entrega() -> None:
    with TestClient(app) as c:
        h = auth(c)
        oid = orden_id("OT-000010")  # PENDING_PAYMENT: diagnóstico 50.000 sin repuestos
        fila = next(o for o in c.get("/api/facturacion/ordenes", headers=h).json() if o["id"] == oid)
        assert (fila["subtotal"], fila["vat"], fila["total"]) == (50000, 9500, 59500)
        assert c.post(f"/api/facturacion/ordenes/{oid}/entregar", headers=h).status_code == 409
        r = c.post(f"/api/facturacion/ordenes/{oid}/pagos", json={"amount": 59000, "method": "CASH"}, headers=h)
        assert r.status_code == 409 and "Diferencia: -500" in r.json()["detail"]
        r = c.post(f"/api/facturacion/ordenes/{oid}/pagos", json={"amount": 59500, "method": "CASH"}, headers=h)
        assert r.status_code == 200 and r.json()["receipt_number"] == "CMP-000004" and r.json()["status"] == "PAID"
        assert c.post(f"/api/facturacion/ordenes/{oid}/pagos", json={"amount": 59500}, headers=h).status_code == 409
        r = c.post(f"/api/facturacion/ordenes/{oid}/entregar", headers=h)
        assert r.status_code == 200 and r.json()["status"] == "DELIVERED"
        token = r.json()["survey_url"].rsplit("/", 1)[1]
        assert c.post(f"/api/encuestas/{token}", json={"score": 5}).status_code == 200
        assert c.post(f"/api/encuestas/{token}", json={"score": 1}).status_code == 409


def test_liquidar_solo_finalizada_y_ticket() -> None:
    with TestClient(app) as c:
        h = auth(c)
        r = c.post(f"/api/facturacion/ordenes/{orden_id('OT-000001')}/liquidar", headers=h)
        assert (r.status_code, r.json()["detail"]) == (
            409, "No se puede facturar una orden de trabajo que no ha sido finalizada por el mecánico")
        oid = orden_id("OT-000003")  # FINISHED: 50.000 + controlador 380.000
        r = c.post(f"/api/facturacion/ordenes/{oid}/liquidar", headers=h)
        assert r.status_code == 200 and (r.json()["total"], r.json()["status"]) == (511700, "PENDING_PAYMENT")
        oid1 = orden_id("OT-000001")
        assert c.get(f"/api/facturacion/ordenes/{oid1}/ticket?codigo=K7M2QX9P4T", headers=h).json()["tracking_code"] == "K7M2QX9P4T"
        assert c.get(f"/api/facturacion/ordenes/{oid1}/ticket?codigo=AAAAAAAAAA", headers=h).status_code == 409
        assert c.get(f"/api/facturacion/ordenes/{oid1}/ticket", headers=h).json()["tracking_code"] is None


def test_encuesta_pendiente_semilla() -> None:
    with TestClient(app) as c:
        assert c.get("/api/encuestas/ENC-O9-PENDIENTE").json()["answered"] is False
        assert c.get("/api/encuestas/NO-EXISTE").status_code == 404
        assert c.post("/api/encuestas/ENC-O9-PENDIENTE", json={"score": 6}).status_code == 422
