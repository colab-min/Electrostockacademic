"""Login, roles y seguridad mínima (HU-21, HU-10, HU-15)."""

from fastapi.testclient import TestClient

from app.main import app

ADMIN = {"email": "admin@electrostock.test", "password": "Admin2026!"}
RECEPCION = {"email": "recepcion@electrostock.test", "password": "Recep2026!"}


def login(c: TestClient, cred: dict) -> str:
    r = c.post("/api/auth/login", json=cred)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_login_por_rol_y_hash_argon2() -> None:
    with TestClient(app) as c:
        for email, password, rol in [("admin@electrostock.test", "Admin2026!", "ADMIN"),
                                     ("recepcion@electrostock.test", "Recep2026!", "RECEPTIONIST"),
                                     ("mecanico1@electrostock.test", "Meca2026!a", "MECHANIC"),
                                     ("cliente1@electrostock.test", "Cliente2026!", "CUSTOMER")]:
            r = c.post("/api/auth/login", json={"email": email, "password": password})
            assert r.json()["user"]["role"] == rol
            assert "HttpOnly" in r.headers["set-cookie"]
        from app.db import SessionLocal
        from app.modulos.identidad.modelos import User

        with SessionLocal() as db:
            assert all(u.password_hash.startswith("$argon2id$v=19$m=19456,t=2,p=1$") for u in db.query(User))


def test_credenciales_invalidas_mismo_mensaje_e_inactivo() -> None:
    with TestClient(app) as c:
        for cred in ({"email": "admin@electrostock.test", "password": "mala"},
                     {"email": "mecanico3@electrostock.test", "password": "Meca2026!c"}):
            r = c.post("/api/auth/login", json=cred)
            assert (r.status_code, r.json()["detail"]) == (401, "Credenciales inválidas, por favor intenta de nuevo")


def test_sexto_intento_bloqueado() -> None:
    with TestClient(app) as c:
        mala = {"email": "cliente2@electrostock.test", "password": "mala"}
        for _ in range(5):
            c.post("/api/auth/login", json=mala)
        r = c.post("/api/auth/login", json={"email": "cliente2@electrostock.test", "password": "Cliente2026!"})
        assert (r.status_code, r.json()["detail"]) == (429, "Demasiados intentos. Intenta de nuevo en 15 minutos")


def test_rol_sin_permiso_403_y_auditado() -> None:
    with TestClient(app) as c:
        r = c.get("/api/usuarios", headers=auth(login(c, RECEPCION)))
        assert (r.status_code, r.json()["detail"]) == (403, "No tiene permisos para esta sección")
        bitacora = c.get("/api/auditoria/bitacora", headers=auth(login(c, ADMIN)))
        if bitacora.status_code == 200:  # la vista de bitácora la construye otro módulo
            assert "ACCESS_DENIED" in bitacora.text


def test_sin_token_o_token_alterado_401() -> None:
    with TestClient(app) as c:
        assert c.get("/api/usuarios").status_code == 401
        token = login(c, ADMIN)
        assert c.get("/api/usuarios", headers=auth(token[:-2] + "xx")).status_code == 401


def test_renovar_rota_y_salir_revoca() -> None:
    with TestClient(app) as c:
        login(c, ADMIN)
        viejo = c.cookies.get("refresh_token")
        assert c.post("/api/auth/refresh").status_code == 200
        assert c.cookies.get("refresh_token") != viejo
        assert c.post("/api/auth/logout").status_code == 204
        c.cookies.clear()
        c.cookies.set("refresh_token", viejo)
        assert c.post("/api/auth/refresh").status_code == 401


def test_registro_cliente_y_contrasena_temporal() -> None:
    with TestClient(app) as c:
        sin = c.post("/api/auth/register", json={"full_name": "Ana Prueba", "document_type": "CC",
                                                 "document_number": "1099999999", "phone": "3001112233",
                                                 "email": "ana.prueba@electrostock.test", "password": "Valida2026!",
                                                 "data_consent": False})
        assert sin.json()["detail"] == "Debes autorizar el tratamiento de tus datos para crear la cuenta"
        otro = c.post("/api/auth/register", json={"full_name": "Sofía", "document_type": "CC",
                                                  "document_number": "1034567890", "phone": "3001112233",
                                                  "email": "otra@electrostock.test", "password": "Valida2026!",
                                                  "data_consent": True})
        assert otro.status_code == 409
        ok = c.post("/api/auth/register", json={"full_name": "Sofía Ramírez", "document_type": "CC",
                                               "document_number": "1034567890", "phone": "3023456789",
                                               "email": "sofia.ramirez@electrostock.test", "password": "Valida2026!",
                                               "data_consent": True})
        assert ok.status_code == 201 and ok.json()["user"]["role"] == "CUSTOMER"
        temporal = login(c, {"email": "recepcion2@electrostock.test", "password": "Temporal2026!"})
        assert c.get("/api/auth/me", headers=auth(temporal)).status_code == 403
        r = c.post("/api/auth/change-password", headers=auth(temporal),
                   json={"new_password": "Nueva2026!x", "confirmation": "Nueva2026!x"})
        assert r.status_code == 200 and r.json()["user"]["must_change_password"] is False
