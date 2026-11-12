"""Órdenes: crear desde cita (HU-23), ingreso sin cita (HU-03/04), estados (HU-05) y seguimiento (HU-07)."""

from datetime import datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.modulos.agenda.modelos import Appointment, AppointmentSlot, Slot
from app.modulos.clientes.modelos import Vehicle
from app.modulos.inventario.modelos import Part, PartReservation
from app.modulos.ordenes import rutas as ordenes_rutas
from app.modulos.ordenes import servicios as ordenes_servicios
from app.modulos.ordenes.modelos import WorkOrder, WorkOrderSlot
from app.seguridad import sha256

RECEPCION = {"email": "recepcion@electrostock.test", "password": "Recep2026!"}
ADMIN = {"email": "admin@electrostock.test", "password": "Admin2026!"}
MECA1 = {"email": "mecanico1@electrostock.test", "password": "Meca2026!a"}
MECA2 = {"email": "mecanico2@electrostock.test", "password": "Meca2026!b"}


def auth(c: TestClient, cred: dict) -> dict:
    r = c.post("/api/auth/login", json=cred)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def orden(numero: str) -> WorkOrder:
    with SessionLocal() as db:
        wo = db.scalar(select(WorkOrder).where(WorkOrder.number == numero))
        assert wo
        return wo


def vehiculo(serie: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Vehicle.id).where(Vehicle.serial_number == serie))  # type: ignore[return-value]


def cita9() -> Appointment:
    with SessionLocal() as db:
        cita = db.scalar(select(Appointment).where(Appointment.code.like("CITA-%-0009")))
        assert cita
        return cita


def test_crear_orden_desde_cita_y_duplicada() -> None:
    with TestClient(app) as c:
        h = auth(c, RECEPCION)
        assert any(x["code"] == cita9().code for x in c.get("/api/ordenes/citas-del-dia?q=BI-48-0010", headers=h).json())
        cita = cita9()
        with SessionLocal() as db:
            cupos = {s.id: s.booked_count for s in db.scalars(select(Slot).join(AppointmentSlot, AppointmentSlot.slot_id == Slot.id)
                                                                 .where(AppointmentSlot.appointment_id == cita.id))}
        r = c.post("/api/ordenes", json={"appointment_id": cita.id}, headers=h)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["number"] == "OT-000011" and body["status"] == "RECEIVED"
        codigo = body["tracking_code"]
        assert len(codigo) == 10 and not set(codigo) & set("IO01")
        with SessionLocal() as db:
            wo = db.get(WorkOrder, body["id"])
            assert wo and wo.tracking_code_hash == sha256(codigo)
            assert db.get(Appointment, cita.id).status == "ATTENDED"  # type: ignore[union-attr]
            reservas = db.scalars(select(PartReservation).where(PartReservation.appointment_id == cita.id)).all()
            assert reservas and all(r.work_order_id == wo.id and r.expires_at is None for r in reservas)
            assert set(db.scalars(select(WorkOrderSlot.slot_id).where(WorkOrderSlot.work_order_id == wo.id))) == set(cupos)
            assert {s.id: s.booked_count for s in db.scalars(select(Slot).where(Slot.id.in_(cupos)))} == cupos
        # el código solo se entrega una vez: el detalle no lo trae
        assert "tracking_code" not in c.get(f"/api/ordenes/{body['id']}", headers=h).json()
        # misma cita otra vez: ya no está vigente; otro ingreso del vehículo: orden activa
        assert c.post("/api/ordenes", json={"appointment_id": cita.id}, headers=h).status_code == 409
        r = c.post("/api/ordenes/ingreso", headers=h, json={"vehicle_id": cita.vehicle_id, "fault_type_id": 1, "service_id": 1})
        assert (r.status_code, r.json()["detail"]) == (409, "El vehículo ya tiene una orden activa (N° OT-000011) en proceso")


def test_cancelar_libera_reservas_y_rechaza_en_diagnostico() -> None:
    with TestClient(app) as c:
        h = auth(c, RECEPCION)
        wo6 = orden("OT-000006")  # ASSIGNED con pastillas reservadas
        with SessionLocal() as db:
            reservado = db.get(Part, 6).reserved_stock  # type: ignore[union-attr]
        r = c.post(f"/api/ordenes/{wo6.id}/cancelar", json={}, headers=h)
        assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
        with SessionLocal() as db:
            assert db.get(Part, 6).reserved_stock == reservado - 1  # type: ignore[union-attr]
        wo8 = orden("OT-000008")  # DIAGNOSING
        r = c.post(f"/api/ordenes/{wo8.id}/cancelar", json={}, headers=h)
        assert r.status_code == 409
        assert r.json()["detail"].startswith("Esta orden no puede pasar de En diagnóstico a Cancelada.")


def test_transiciones_valida_invalida_ajena_y_version() -> None:
    with TestClient(app) as c:
        h2 = auth(c, MECA2)
        wo = orden("OT-000006")
        assert [t["to_status"] for t in c.get(f"/api/ordenes/{wo.id}/transiciones", headers=h2).json()] == ["DIAGNOSING"]
        r = c.post(f"/api/ordenes/{wo.id}/estado", json={"to_status": "FINISHED", "version": wo.version}, headers=h2)
        assert (r.status_code, r.json()["detail"]) == (
            409, "Esta orden no puede pasar de Asignada a Finalizada. Pasos válidos: En diagnóstico.")
        h1 = auth(c, MECA1)
        assert c.get(f"/api/ordenes/{wo.id}", headers=h1).status_code == 404
        assert c.post(f"/api/ordenes/{wo.id}/estado", json={"to_status": "DIAGNOSING", "version": wo.version},
                      headers=h1).status_code == 404
        r = c.post(f"/api/ordenes/{wo.id}/estado", json={"to_status": "DIAGNOSING", "version": wo.version}, headers=h2)
        assert r.status_code == 200 and r.json()["status"] == "DIAGNOSING"
        assert r.json()["history"][-1]["to_status"] == "DIAGNOSING"
        r = c.post(f"/api/ordenes/{wo.id}/estado", json={"to_status": "REPAIRING", "version": wo.version}, headers=h2)
        assert (r.status_code, r.json()["detail"]) == (409, "La orden fue modificada por otro usuario, actualice la vista")
        r = c.patch(f"/api/ordenes/{wo.id}/diagnostico", json={"diagnosis": "Pastillas gastadas", "version": wo.version + 1},
                    headers=h2)
        assert r.status_code == 200 and r.json()["diagnosis"] == "Pastillas gastadas" and r.json()["status"] == "DIAGNOSING"


def test_finalizar_con_repuesto_reservado_e_instalar() -> None:
    with TestClient(app) as c:
        h1 = auth(c, MECA1)
        wo = orden("OT-000001")  # REPAIRING con batería 60V reservada
        r = c.post(f"/api/ordenes/{wo.id}/estado", json={"to_status": "FINISHED", "version": wo.version}, headers=h1)
        assert r.status_code == 409 and "Batería litio 60V 20Ah" in r.json()["detail"]
        linea = c.get(f"/api/ordenes/{wo.id}", headers=h1).json()["parts"][0]
        r = c.post(f"/api/ordenes/{wo.id}/repuestos/{linea['id']}/instalar", headers=h1)
        assert r.status_code == 200 and r.json()["parts"][0]["status"] == "INSTALLED"
        with SessionLocal() as db:
            p = db.get(Part, 2)
            assert p and (p.physical_stock, p.reserved_stock) == (0, 0)
        r = c.post(f"/api/ordenes/{wo.id}/estado", json={"to_status": "FINISHED", "version": r.json()["version"]}, headers=h1)
        assert r.status_code == 200 and r.json()["status"] == "FINISHED"


def test_agregar_repuesto_sin_stock_y_servicio() -> None:
    with TestClient(app) as c:
        h1 = auth(c, MECA1)
        wo = orden("OT-000008")  # DIAGNOSING, scooter de 36 V
        r = c.post(f"/api/ordenes/{wo.id}/repuestos", json={"part_id": 7, "quantity": 99}, headers=h1)
        assert r.status_code == 409 and r.json()["detail"].startswith("Cantidad solicitada supera el stock disponible")
        r = c.post(f"/api/ordenes/{wo.id}/repuestos", json={"part_id": 7, "quantity": 1}, headers=h1)
        assert r.status_code == 201 and r.json()["parts"][-1]["status"] == "RESERVED"
        r = c.post(f"/api/ordenes/{wo.id}/servicios", json={"service_id": 8}, headers=h1)
        assert r.status_code == 201 and "Cambio de neumático" in r.json()["services"]


def test_asignacion_mecanico_activo() -> None:
    with TestClient(app) as c:
        h = auth(c, ADMIN)
        wo = orden("OT-000005")
        r = c.post(f"/api/ordenes/{wo.id}/asignacion", json={"mechanic_id": 5}, headers=h)  # mecánico inactivo
        assert (r.status_code, r.json()["detail"]) == (409, "El mecánico seleccionado no se encuentra activo o disponible")
        r = c.post(f"/api/ordenes/{wo.id}/asignacion", json={"mechanic_id": 4, "version": wo.version}, headers=h)
        assert r.status_code == 200 and r.json()["status"] == "ASSIGNED"
        assert any(o["id"] == wo.id for o in c.get("/api/ordenes/mias", headers=auth(c, MECA2)).json())


def _hoy_a(monkeypatch: pytest.MonkeyPatch, h: int, m: int) -> None:
    hoy = ordenes_servicios.ahora().date()
    monkeypatch.setattr(ordenes_servicios, "ahora", lambda: datetime.combine(hoy, time(h, m)))


def test_ingreso_sin_cita_ubicado_y_en_cola(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as c:
        h = auth(c, RECEPCION)
        _hoy_a(monkeypatch, 9, 40)
        r = c.post("/api/ordenes/ingreso", headers=h, json={"vehicle_id": vehiculo("MR-84-0016"), "fault_type_id": 1})
        assert (r.status_code, r.json()["detail"]) == (422, "Seleccione el servicio")
        r = c.post("/api/ordenes/ingreso", headers=h,
                   json={"vehicle_id": vehiculo("MR-84-0016"), "fault_type_id": 1, "service_id": 5})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["priority"] == "HIGH" and body["queue_position"] is None and body["tracking_code"]
        assert body["estimated_delivery_at"].endswith("T11:00:00")  # franja de las 10:00 + 60 min
        # 15:40 y 3 horas de servicio: no caben 16:00-17:00 -> cola con hora estimada
        _hoy_a(monkeypatch, 15, 40)
        r = c.post("/api/ordenes/ingreso", headers=h,
                   json={"vehicle_id": vehiculo("PT-48-0014"), "fault_type_id": 4, "service_id": 6})
        assert r.status_code == 201, r.text
        assert r.json()["queue_position"] is not None and r.json()["hora_estimada"]
        cola = c.get("/api/ordenes/cola", headers=h).json()
        assert [o["priority"] for o in cola] == sorted((o["priority"] for o in cola), key=["HIGH", "MEDIUM", "LOW"].index)
        assert any(o["id"] == r.json()["id"] for o in cola)
        # vehículo con cita activa: se crea desde la cita
        r = c.post("/api/ordenes/ingreso", headers=h,
                   json={"vehicle_id": vehiculo("BI-36-0012"), "fault_type_id": 1, "service_id": 1})
        assert r.status_code == 409 and "Cree la orden desde esa cita" in r.json()["detail"]


def test_cola_falla_corta_adelanta_solo_misma_prioridad(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as c:
        h = auth(c, RECEPCION)
        _hoy_a(monkeypatch, 17, 30)  # ya no hay franjas hoy: todo va a la cola
        ids = {}
        for serie, falla in (("PT-48-0014", 3), ("MR-84-0016", 5)):  # Media y Luces (15 min, Baja)
            ids[falla] = c.post("/api/ordenes/ingreso", headers=h,
                                json={"vehicle_id": vehiculo(serie), "fault_type_id": falla, "service_id": 1}).json()["id"]
        corta = c.post("/api/ordenes/ingreso", headers=h,  # Ajuste de freno: 10 min, Baja
                       json={"vehicle_id": vehiculo("SC-48-0001"), "fault_type_id": 6, "service_id": 7}).json()["id"]
        orden_cola = [o["id"] for o in c.get("/api/ordenes/cola", headers=h).json()]
        assert orden_cola.index(ids[3]) < orden_cola.index(corta) < orden_cola.index(ids[5])


def test_seguimiento_lista_blanca_invalido_y_limite() -> None:
    ordenes_rutas.seguimiento_limiter.failures.clear()
    with TestClient(app) as c:
        r = c.get("/api/seguimiento/K7M2QX9P4T")
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"tipo", "modelo", "estado", "estado_publico", "linea_tiempo", "entrega_estimada"}
        assert body["modelo"] == "NIU NQi GTS" and body["estado_publico"] == "En reparación"
        assert [x["titulo"] for x in body["linea_tiempo"]] == ["Recibido", "En diagnóstico", "En reparación"]
        assert "MO-60-0008" not in r.text and "Batería" not in r.text
        assert c.get("/api/seguimiento/M8E3K6T4ZD").json()["estado_publico"] == "Recibido"
        for malo in ("AAAAAAAAAA", "<script>", "K7M2QX9P4"):
            r = c.get(f"/api/seguimiento/{malo}")
            assert (r.status_code, r.json()["detail"]) == (
                404, "No encontramos información con ese código. Verifica e intenta de nuevo.")
        for _ in range(25):
            c.get("/api/seguimiento/K7M2QX9P4T")
        r = c.get("/api/seguimiento/K7M2QX9P4T")
        assert (r.status_code, r.json()["detail"]) == (429, "Demasiadas consultas, espera un momento")
    ordenes_rutas.seguimiento_limiter.failures.clear()


def test_tarea_ubica_la_cola_al_liberarse_cupo(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as c:
        h = auth(c, RECEPCION)
        _hoy_a(monkeypatch, 9, 40)
        assert c.post(f"/api/ordenes/{orden('OT-000006').id}/cancelar", json={}, headers=h).status_code == 200
        with SessionLocal() as db:
            ordenes_servicios.ubicar_cola(db)
            db.commit()
        wo5 = orden("OT-000005")  # estaba en cola: ahora ocupa la franja de las 10:00
        assert wo5.queue_position is None and wo5.estimated_delivery_at.hour == 10  # type: ignore[union-attr]
