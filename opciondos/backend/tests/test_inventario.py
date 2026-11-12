"""HU-08, HU-27, HU-29 (lo básico)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def hdr():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"email": "admin@electrostock.test", "password": "Admin2026!"})
        yield c, {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_alertas_movimientos_y_sku(hdr):
    c, h = hdr
    partes = {p["sku"]: p for p in c.get("/api/inventario/repuestos", headers=h).json()}
    assert {s for s, p in partes.items() if p["alerta"]} >= {"BAT-60-20", "CAR-48-2A"}
    r = c.post("/api/inventario/movimientos", headers=h, json={"part_id": partes["CAR-48-2A"]["id"], "type": "IN", "quantity": 5})
    assert r.status_code == 201 and r.json()["physical_stock"] == 5 and not r.json()["alerta"]
    bat = partes["BAT-60-20"]
    r = c.post("/api/inventario/movimientos", headers=h,
               json={"part_id": bat["id"], "type": "WRITE_OFF", "quantity": 1, "reason": "Daño"})
    assert r.status_code == 409 and "Libere reservas primero" in r.json()["detail"]
    r = c.post("/api/inventario/repuestos", headers=h, json={"sku": "BAT-48-15", "name": "x", "category": "BATTERY",
                                                             "purchase_price": 1, "sale_price": 2})
    assert r.status_code == 409 and r.json()["detail"] == "El código de repuesto ingresado ya existe en el inventario"
