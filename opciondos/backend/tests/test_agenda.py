"""HU-01, HU-11, HU-19, HU-28 contra la base del agente (RESET_SEED=true recarga la semilla al arrancar)."""

import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.db import SessionLocal
from app.main import app
from app.modulos.agenda import servicios as agenda
from app.modulos.agenda.modelos import Appointment, AppointmentSlot, Slot
from app.modulos.catalogo.modelos import Service
from app.modulos.clientes.modelos import Vehicle
from app.modulos.inventario.modelos import Part
from app.tiempo import ahora

MARIA, JULIAN = ("cliente1@electrostock.test", "Cliente2026!"), ("cliente2@electrostock.test", "Cliente2026!")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def h(client: TestClient, cred: tuple[str, str]) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"email": cred[0], "password": cred[1]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def ids() -> dict[str, int]:
    with SessionLocal() as db:
        out = {v.serial_number: v.id for v in db.scalars(select(Vehicle))}
        out |= {s.code: s.id for s in db.scalars(select(Service))}
        return out


def reservado(sku: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Part.reserved_stock).where(Part.sku == sku))


def ocupados(fecha: str, hora: str) -> int:
    with SessionLocal() as db:
        return db.scalar(select(Slot.booked_count).where(Slot.slot_date == date.fromisoformat(fecha),
                                                         Slot.start_time == f"{hora}:00"))


def hueco(client: TestClient, hdr: dict, service_id: int, saltar: int = 0) -> tuple[str, str]:
    """Primer (fecha, hora) libre a partir de mañana; `saltar` descarta los primeros."""
    hoy = ahora().date()
    for mes in (hoy.replace(day=1), (hoy.replace(day=1) + timedelta(days=32)).replace(day=1)):
        dias = client.get("/api/agenda/disponibilidad", params={"service_id": service_id, "mes": f"{mes:%Y-%m}"},
                          headers=hdr).json()["dias"]
        for fecha in sorted(d for d, e in dias.items() if e == "disponible" and d > hoy.isoformat()):
            for f in client.get("/api/agenda/franjas", params={"service_id": service_id, "fecha": fecha},
                                headers=hdr).json():
                if f["estado"] == "libre":
                    if saltar == 0:
                        return fecha, f["hora"]
                    saltar -= 1
    raise AssertionError("sin huecos")


def test_agendar_y_confirmar_reserva_franja_y_repuesto(client):
    hdr, i = h(client, MARIA), ids()
    fecha, hora = hueco(client, hdr, i["CAMB-BAT-48"])
    antes_slot, antes_bat = ocupados(fecha, hora), reservado("BAT-48-15")
    r = client.post("/api/agenda/citas", headers=hdr, json={"vehicle_id": i["SC-48-0001"],
                                                            "service_id": i["CAMB-BAT-48"], "fecha": fecha, "hora": hora})
    assert r.status_code == 201, r.text
    cita = r.json()
    assert cita["status"] == "HELD" and cita["repuestos"] == [{"name": "Batería litio 48V 15Ah", "quantity": 1}]
    assert ocupados(fecha, hora) == antes_slot + 1 and reservado("BAT-48-15") == antes_bat + 1
    r = client.post(f"/api/agenda/citas/{cita['id']}/confirmar", headers=hdr)
    assert r.status_code == 200 and r.json()["status"] == "CONFIRMED"
    assert re.fullmatch(r"CITA-\d{8}-\d{4}", r.json()["code"]) and r.json()["limite_cambio"]
    # el mismo vehículo no puede tener otra cita activa (RN-13)
    otro = hueco(client, hdr, i["DIAG"], saltar=3)
    r = client.post("/api/agenda/citas", headers=hdr, json={"vehicle_id": i["SC-48-0001"], "service_id": i["DIAG"],
                                                            "fecha": otro[0], "hora": otro[1]})
    assert r.status_code == 409 and "ya tiene una cita vigente" in r.json()["detail"]
    # cancelar libera franja y repuesto
    r = client.post(f"/api/agenda/citas/{cita['id']}/cancelar", headers=hdr)
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert ocupados(fecha, hora) == antes_slot and reservado("BAT-48-15") == antes_bat


def test_rechazo_por_repuesto_sin_disponible(client):
    hdr, i = h(client, MARIA), ids()
    fecha, hora = hueco(client, hdr, i["DIAG"])
    antes = ocupados(fecha, hora)
    r = client.post("/api/agenda/citas", headers=hdr, json={"vehicle_id": i["SC-48-0001"],
                                                            "service_id": i["CAMB-BAT-60"], "fecha": fecha, "hora": hora})
    assert r.status_code == 409
    assert r.json()["detail"] == "No tenemos Batería litio 60V 20Ah disponible para este servicio en este momento."
    assert ocupados(fecha, hora) == antes


def test_voltaje_incompatible_exige_motivo(client):
    hdr, i = h(client, MARIA), ids()
    fecha, hora = hueco(client, hdr, i["CAMB-BAT-48"])
    body = {"vehicle_id": i["PT-36-0002"], "service_id": i["CAMB-BAT-48"], "fecha": fecha, "hora": hora}
    r = client.post("/api/agenda/citas", headers=hdr, json=body)
    assert r.status_code == 409 and r.json()["detail"].startswith("Riesgo eléctrico")
    r = client.post("/api/agenda/citas", headers=hdr, json=body | {"motivo_voltaje": "Conversión a 48V acordada"})
    assert r.status_code == 201
    assert client.post(f"/api/agenda/citas/{r.json()['id']}/cancelar", headers=hdr).status_code == 200


def test_franja_llena_sugiere_otra(client):
    hdr, i = h(client, MARIA), ids()
    fecha, hora = hueco(client, hdr, i["DIAG"])
    cond = (Slot.slot_date == date.fromisoformat(fecha)) & (Slot.start_time == f"{hora}:00")
    with SessionLocal() as db:
        antes = db.scalar(select(Slot.booked_count).where(cond))
        db.execute(update(Slot).where(cond).values(booked_count=Slot.capacity))
        db.commit()
    try:
        r = client.post("/api/agenda/citas", headers=hdr, json={"vehicle_id": i["SC-48-0001"], "service_id": i["DIAG"],
                                                                "fecha": fecha, "hora": hora})
        assert r.status_code == 409 and r.json()["detail"].startswith("Alguien acaba de tomar este cupo. Te sugerimos")
    finally:
        with SessionLocal() as db:
            db.execute(update(Slot).where(cond).values(booked_count=antes))
            db.commit()


def _held(client, hdr, i) -> dict:
    fecha, hora = hueco(client, hdr, i["CAMB-BAT-48"])
    r = client.post("/api/agenda/citas", headers=hdr, json={"vehicle_id": i["SC-48-0001"],
                                                            "service_id": i["CAMB-BAT-48"], "fecha": fecha, "hora": hora})
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        db.execute(update(Appointment).where(Appointment.id == r.json()["id"])
                   .values(hold_expires_at=ahora() - timedelta(minutes=1)))
        db.commit()
    return r.json() | {"fecha": fecha, "hora": hora}


def test_bloqueo_vencido_410(client):
    hdr, i = h(client, MARIA), ids()
    antes_bat = reservado("BAT-48-15")
    cita = _held(client, hdr, i)
    r = client.post(f"/api/agenda/citas/{cita['id']}/confirmar", headers=hdr)
    assert r.status_code == 410 and r.json()["detail"] == "Tu reserva expiró"
    assert reservado("BAT-48-15") == antes_bat


def test_tarea_expiracion_idempotente(client):
    hdr, i = h(client, MARIA), ids()
    antes_bat = reservado("BAT-48-15")
    cita = _held(client, hdr, i)
    antes_slot = ocupados(cita["fecha"], cita["hora"])
    for _ in range(2):
        with SessionLocal() as db:
            agenda.expirar_citas(db)
            db.commit()
    with SessionLocal() as db:
        assert db.get(Appointment, cita["id"]).status == "EXPIRED"
    assert ocupados(cita["fecha"], cita["hora"]) == antes_slot - 1 and reservado("BAT-48-15") == antes_bat


def _cita_ct2(client, hdr) -> dict:
    return next(c for c in client.get("/api/agenda/citas/mias", headers=hdr).json()
                if c["vehicle"]["serial_number"] == "SC-48-0009")


def test_cita_ajena_404(client):
    cita = _cita_ct2(client, h(client, MARIA))
    hdr = h(client, JULIAN)
    assert client.post(f"/api/agenda/citas/{cita['id']}/cancelar", headers=hdr).status_code == 404
    r = client.post(f"/api/agenda/citas/{cita['id']}/reprogramar", headers=hdr, json={"fecha": "2030-01-02", "hora": "09:00"})
    assert r.status_code == 404


def test_reprogramar_fuera_de_ventana_y_dentro(client):
    hdr, i = h(client, MARIA), ids()
    cita = _cita_ct2(client, hdr)
    original = cita["starts_at"]
    with SessionLocal() as db:
        db.execute(update(Appointment).where(Appointment.id == cita["id"])
                   .values(starts_at=ahora() + timedelta(minutes=30)))
        db.commit()
    try:
        fecha, hora = hueco(client, hdr, i["CAMB-BAT-48"])
        for accion, body in (("reprogramar", {"fecha": fecha, "hora": hora}), ("cancelar", None)):
            r = client.post(f"/api/agenda/citas/{cita['id']}/{accion}", headers=hdr, json=body)
            assert r.status_code == 409 and r.json()["detail"].startswith("Ya no es posible cancelar")
    finally:
        with SessionLocal() as db:
            db.execute(update(Appointment).where(Appointment.id == cita["id"]).values(starts_at=original))
            db.commit()
    # dentro de la ventana: mueve franjas y conserva la reserva
    antes_bat = reservado("BAT-48-15")
    fecha, hora = hueco(client, hdr, i["CAMB-BAT-48"], saltar=1)
    antes_nueva = ocupados(fecha, hora)
    r = client.post(f"/api/agenda/citas/{cita['id']}/reprogramar", headers=hdr, json={"fecha": fecha, "hora": hora})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "RESCHEDULED" and r.json()["repuestos"]
    assert ocupados(fecha, hora) == antes_nueva + 1 and reservado("BAT-48-15") == antes_bat
    with SessionLocal() as db:
        assert len(list(db.scalars(select(AppointmentSlot).where(AppointmentSlot.appointment_id == cita["id"])))) == 1


def test_reparacion_motor_no_ofrece_inicios_tardios(client):
    hdr, i = h(client, MARIA), ids()
    fecha, _ = hueco(client, hdr, i["REP-MOT"])
    libres = [f["hora"] for f in client.get("/api/agenda/franjas", params={"service_id": i["REP-MOT"], "fecha": fecha},
                                            headers=hdr).json() if f["estado"] == "libre"]
    assert libres and all(x <= "15:00" for x in libres)
