"""Rutas del módulo ordenes: /api/ordenes y /api/seguimiento."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.modulos.ordenes import servicios
from app.modulos.ordenes.esquemas import (AsignacionIn, CancelarIn, CrearDesdeCitaIn, DiagnosticoIn, EstadoIn,
                                          IngresoIn, RepuestoIn, ServicioIn)
from app.seguridad import CurrentUser, LoginLimiter, require_roles

router = APIRouter(tags=["ordenes"])
RECEPCION = require_roles("RECEPTIONIST", "ADMIN")
MECANICO = require_roles("MECHANIC")
seguimiento_limiter = LoginLimiter(limit=30, window_s=60)  # 30 consultas por minuto por IP (HU-07)


@router.get("/ordenes/citas-del-dia")
def citas_del_dia(q: str | None = None, _: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> list[dict]:
    return servicios.citas_del_dia(db, q)


@router.post("/ordenes", status_code=201)
def crear(body: CrearDesdeCitaIn, user: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> dict:
    return servicios.crear_desde_cita(db, body.appointment_id, body.intake_reason, user)


@router.post("/ordenes/ingreso", status_code=201)
def ingreso(body: IngresoIn, user: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> dict:
    return servicios.ingreso_sin_cita(db, body.vehicle_id, body.fault_type_id, body.service_id, body.intake_reason, user)


@router.get("/ordenes/cola")
def cola(_: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> list[dict]:
    return servicios.cola(db)


@router.get("/ordenes/mias")
def mias(user: CurrentUser = Depends(MECANICO), db: Session = Depends(get_db)) -> list[dict]:
    return servicios.mias(db, user)


@router.get("/ordenes")
def listar(estado: str | None = None, _: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> list[dict]:
    return servicios.listar(db, estado)


@router.get("/ordenes/{order_id}")
def detalle(order_id: int, user: CurrentUser = Depends(require_roles("MECHANIC", "RECEPTIONIST", "ADMIN")),
            db: Session = Depends(get_db)) -> dict:
    return servicios.detalle(db, servicios.orden_para(db, order_id, user))


@router.get("/ordenes/{order_id}/transiciones")
def transiciones(order_id: int, user: CurrentUser = Depends(require_roles("MECHANIC", "RECEPTIONIST", "ADMIN")),
                 db: Session = Depends(get_db)) -> list[dict]:
    return servicios.transiciones(servicios.orden_para(db, order_id, user), user.role)


@router.post("/ordenes/{order_id}/estado")
def estado(order_id: int, body: EstadoIn, user: CurrentUser = Depends(MECANICO), db: Session = Depends(get_db)) -> dict:
    return servicios.avanzar(db, order_id, user, body.to_status, body.version, body.reason)


@router.post("/ordenes/{order_id}/cancelar")
def cancelar(order_id: int, body: CancelarIn, user: CurrentUser = Depends(RECEPCION), db: Session = Depends(get_db)) -> dict:
    return servicios.cancelar(db, order_id, user, body.reason, body.version)


@router.post("/ordenes/{order_id}/asignacion")
def asignacion(order_id: int, body: AsignacionIn, user: CurrentUser = Depends(require_roles("ADMIN")),
               db: Session = Depends(get_db)) -> dict:
    return servicios.asignar(db, order_id, body.mechanic_id, body.version, user)


@router.patch("/ordenes/{order_id}/diagnostico")
def diagnostico(order_id: int, body: DiagnosticoIn, user: CurrentUser = Depends(MECANICO),
                db: Session = Depends(get_db)) -> dict:
    return servicios.diagnosticar(db, order_id, body.diagnosis, body.version, user)


@router.post("/ordenes/{order_id}/repuestos", status_code=201)
def agregar_repuesto(order_id: int, body: RepuestoIn, user: CurrentUser = Depends(MECANICO),
                     db: Session = Depends(get_db)) -> dict:
    return servicios.agregar_repuesto(db, order_id, body.part_id, body.quantity, body.voltage_reason, user)


@router.post("/ordenes/{order_id}/repuestos/{line_id}/instalar")
def instalar(order_id: int, line_id: int, user: CurrentUser = Depends(MECANICO), db: Session = Depends(get_db)) -> dict:
    return servicios.instalar_repuesto(db, order_id, line_id, user)


@router.post("/ordenes/{order_id}/repuestos/{line_id}/retirar")
def retirar(order_id: int, line_id: int, user: CurrentUser = Depends(MECANICO), db: Session = Depends(get_db)) -> dict:
    return servicios.retirar_repuesto(db, order_id, line_id, user)


@router.post("/ordenes/{order_id}/servicios", status_code=201)
def agregar_servicio(order_id: int, body: ServicioIn, user: CurrentUser = Depends(MECANICO),
                     db: Session = Depends(get_db)) -> dict:
    return servicios.agregar_servicio(db, order_id, body.service_id, user)


@router.get("/seguimiento/{codigo}")
def seguimiento(codigo: str, request: Request, db: Session = Depends(get_db)) -> dict:
    ip = request.client.host if request.client else "-"
    if seguimiento_limiter.blocked(ip):
        raise HTTPException(429, "Demasiadas consultas, espera un momento")
    seguimiento_limiter.fail(ip)  # cuenta cada consulta, no solo las fallidas
    return servicios.seguimiento(db, codigo[:40])
