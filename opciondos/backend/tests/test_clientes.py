"""Clientes y vehículos (HU-22), expediente (HU-06), historial (HU-30), reportes (HU-14) y bitácora (HU-20)."""

from fastapi.testclient import TestClient

from app.main import app

ADMIN = ("admin@electrostock.test", "Admin2026!")
RECEPCION = ("recepcion@electrostock.test", "Recep2026!")
MECANICO = ("mecanico1@electrostock.test", "Meca2026!a")
CLIENTE = ("cliente1@electrostock.test", "Cliente2026!")
CLIENTE2 = ("cliente2@electrostock.test", "Cliente2026!")


def auth(c: TestClient, cred: tuple[str, str]) -> dict:
    r = c.post("/api/auth/login", json={"email": cred[0], "password": cred[1]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def vehiculo(**extra: object) -> dict:
    return {"type": "SCOOTER", "serial_number": "SC-NUEVO-01", "plate": None, "brand": "Xiaomi", "model": "5 Pro",
            "year": 2025, "nominal_voltage_v": 48, "battery_capacity_ah": 12.5, **extra}


def cliente(**extra: object) -> dict:
    return {"document_type": "CC", "document_number": "1099887766", "full_name": "Lucía Prieto", "phone": "3101234567",
            "email": "lucia@example.com", "data_consent": True, "vehicle": vehiculo(), **extra}


def test_registro_cliente_y_vehiculo_y_duplicados() -> None:
    with TestClient(app) as c:
        h = auth(c, RECEPCION)
        r = c.post("/api/clientes", json=cliente(), headers=h)
        assert r.status_code == 201, r.text
        found = c.get("/api/clientes", params={"document_type": "CC", "document_number": "1099887766"}, headers=h).json()
        assert found["vehicles"][0]["serial_number"] == "SC-NUEVO-01" and found["vehicles"][0]["plate"] is None

        r = c.post("/api/clientes", json=cliente(document_number="1099887700"), headers=h)
        assert (r.status_code, r.json()["detail"]) == (409, "El número de serie ingresado ya se encuentra registrado")
        r = c.post("/api/clientes", json=cliente(document_number="1099887700",
                                                 vehicle=vehiculo(serial_number="MO-NUEVA-2", plate="abc12d")), headers=h)
        assert (r.status_code, r.json()["detail"]) == (409, "La placa ingresada ya se encuentra registrada")


def test_sin_casilla_y_formato_invalido() -> None:
    with TestClient(app) as c:
        h = auth(c, RECEPCION)
        r = c.post("/api/clientes", json=cliente(data_consent=False), headers=h)
        assert (r.status_code, r.json()["detail"]) == (422, "Debe registrar la autorización del cliente para continuar")
        r = c.post("/api/clientes", json=cliente(document_number="12AB45", phone=""), headers=h)
        assert r.status_code == 422 and {"document_number", "phone"} <= set(r.json()["fields"])
        r = c.post("/api/clientes", json=cliente(vehicle=vehiculo(plate="AB1234")), headers=h)
        assert r.status_code == 422 and "plate" in r.json()["fields"]


def test_editar_contacto_solo_recepcion() -> None:
    with TestClient(app) as c:
        h = auth(c, RECEPCION)
        sofia = c.get("/api/clientes", params={"document_type": "CC", "document_number": "1034567890"}, headers=h).json()
        assert sofia["full_name"] == "Sofía Ramírez" and not sofia["has_account"]
        body = {"phone": "3200000000", "email": "sofia.nueva@example.com"}
        for cred in (MECANICO, CLIENTE):
            assert c.patch(f"/api/clientes/{sofia['id']}", json=body, headers=auth(c, cred)).status_code == 403
        r = c.patch(f"/api/clientes/{sofia['id']}", json=body, headers=h)
        assert r.status_code == 200 and r.json()["email"] == "sofia.nueva@example.com"
        r = c.post("/api/clientes/vehiculos", json=vehiculo(customer_id=sofia["id"], type="E_BIKE"), headers=h)
        assert r.status_code == 201


def test_vehiculo_propio_del_cliente() -> None:
    with TestClient(app) as c:
        h = auth(c, CLIENTE)
        antes = len(c.get("/api/clientes/mis-vehiculos", headers=h).json())
        r = c.post("/api/clientes/vehiculos", json=vehiculo(type="KICK_SCOOTER", customer_id=999), headers=h)
        assert r.status_code == 201, r.text
        mios = c.get("/api/clientes/mis-vehiculos", headers=h).json()
        assert len(mios) == antes + 1 and "SC-NUEVO-01" in {v["serial_number"] for v in mios}


def test_expediente_busqueda_y_notas() -> None:
    with TestClient(app) as c:
        h = auth(c, MECANICO)
        r = c.get("/api/clientes/vehiculos", params={"q": "abc12d"}, headers=h)
        assert r.json()[0]["serial_number"] == "MO-72-0004" and r.json()[0]["customer"]["full_name"]
        assert c.get("/api/clientes/vehiculos/NO-EXISTE-99/expediente", headers=h).status_code == 404

        exp = c.get("/api/clientes/vehiculos/SC-48-0001/expediente", headers=h).json()
        assert [o["number"] for o in exp["orders"]] == ["OT-000004", "OT-000007"]
        assert exp["orders"][0]["parts"] and len(exp["notes"]) == 1 and exp["vehicle"]["battery_cell"]

        html = '<p><strong>Ok</strong></p><ul><li>uno</li></ul><script>alert(1)</script><img src=x onerror="alert(2)">'
        r = c.post(f"/api/clientes/vehiculos/{exp['vehicle']['id']}/notas", json={"content_html": html}, headers=h)
        assert r.status_code == 201
        nota = c.get("/api/clientes/vehiculos/SC-48-0001/expediente", headers=h).json()["notes"][0]
        assert "<strong>Ok</strong>" in nota["content_html"] and "<li>uno</li>" in nota["content_html"]
        assert "script" not in nota["content_html"] and "onerror" not in nota["content_html"]
        assert nota["author"] == "Andrés Rojas"

        rec = auth(c, RECEPCION)
        assert c.get("/api/clientes/vehiculos/SC-48-0001/expediente", headers=rec).status_code == 200
        r = c.post(f"/api/clientes/vehiculos/{exp['vehicle']['id']}/notas", json={"content_html": "x"}, headers=rec)
        assert r.status_code == 403


def test_historial_propio_y_ajeno() -> None:
    with TestClient(app) as c:
        h = auth(c, CLIENTE)
        sc = next(v for v in c.get("/api/clientes/mis-vehiculos", headers=h).json() if v["serial_number"] == "SC-48-0001")
        hist = c.get(f"/api/clientes/mis-vehiculos/{sc['id']}/historial", headers=h).json()
        assert [o["number"] for o in hist["orders"]] == ["OT-000004", "OT-000007"]
        assert hist["orders"][0]["total_paid"] == 95200
        r = c.get(f"/api/clientes/mis-vehiculos/{sc['id']}/historial", headers=auth(c, CLIENTE2))
        assert r.status_code == 404


def test_reportes_y_bitacora_solo_admin() -> None:
    with TestClient(app) as c:
        h = auth(c, ADMIN)
        r = c.get("/api/reportes/resumen", params={"desde": "2000-01-01", "hasta": "2100-01-01"}, headers=h)
        data = r.json()
        assert r.status_code == 200 and data["ingresos"] == 95200 + 59500 + 95200
        assert sum(e["cantidad"] for e in data["ordenes_por_estado"]) == 10
        assert data["satisfaccion"]["promedio"] == 5.0 and data["repuestos"]
        assert c.get("/api/reportes/resumen", params={"desde": "2026-02-01", "hasta": "2026-01-01"},
                     headers=h).status_code == 422

        assert c.get("/api/auditoria/bitacora", headers=auth(c, RECEPCION)).status_code == 403
        r = c.get("/api/auditoria/bitacora", params={"accion": "ACCESS_DENIED"}, headers=h)
        assert r.status_code == 200 and r.json() and all(e["action"] == "ACCESS_DENIED" for e in r.json())
        assert "ACCESS_DENIED" in c.get("/api/auditoria/opciones", headers=h).json()["acciones"]
