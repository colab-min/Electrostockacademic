"""Facturación: liquidar, cobrar y entregar (HU-13), ticket (HU-17) y encuesta (HU-16)."""

import secrets
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.modulos.auditoria.servicios import registrar
from app.modulos.clientes.modelos import Vehicle
from app.modulos.facturacion.modelos import Payment, Receipt, Survey
from app.modulos.ordenes import servicios as ordenes
from app.modulos.ordenes.modelos import Sequence, WorkOrder, WorkOrderPart, WorkOrderService
from app.seguridad import CurrentUser, sha256
from app.tiempo import ahora

CAJA = ("FINISHED", "PENDING_PAYMENT", "PAID")
ENCUESTA_INVALIDA = "Este enlace de encuesta no es válido."


def montos(db: Session, wo: WorkOrder) -> dict:
    """RN-36: mano de obra + repuestos instalados + IVA sobre el subtotal, en pesos enteros redondeados al peso."""
    mano_obra = sum(db.scalars(select(WorkOrderService.applied_price).where(WorkOrderService.work_order_id == wo.id)))
    repuestos = sum(q * p for q, p in db.execute(select(WorkOrderPart.quantity, WorkOrderPart.unit_price).where(
        WorkOrderPart.work_order_id == wo.id, WorkOrderPart.status == "INSTALLED")))
    subtotal = mano_obra + repuestos
    iva = int((Decimal(subtotal) * Decimal(str(config.VAT_RATE))).quantize(Decimal(1), ROUND_HALF_UP))
    return {"labor": mano_obra, "parts": repuestos, "subtotal": subtotal, "vat": iva, "total": subtotal + iva}


def _caja(db: Session, wo: WorkOrder) -> dict:
    recibo = db.scalar(select(Receipt).where(Receipt.work_order_id == wo.id))
    encuesta = db.scalar(select(Survey).where(Survey.work_order_id == wo.id))
    return {**ordenes.resumen(db, wo), **montos(db, wo), "receipt_number": recibo.number if recibo else None,
            "survey_url": f"/encuesta/{encuesta.token}" if encuesta else None}


def listar(db: Session, estado: str | None) -> list[dict]:
    estados = (estado,) if estado else CAJA
    return [_caja(db, wo) for wo in db.scalars(select(WorkOrder).where(WorkOrder.status.in_(estados))
                                               .order_by(WorkOrder.created_at))]


def liquidar(db: Session, order_id: int, user: CurrentUser) -> dict:
    wo = ordenes.orden_para(db, order_id, user, lock=True)
    if wo.status != "FINISHED":
        raise HTTPException(409, "No se puede facturar una orden de trabajo que no ha sido finalizada por el mecánico")
    if montos(db, wo)["total"] <= 0:
        raise HTTPException(409, "El total de la orden es cero o negativo. Verifique tarifas y repuestos.")
    ordenes.cambiar_estado(db, wo, "PENDING_PAYMENT", user)
    db.commit()
    return _caja(db, wo)


def pagar(db: Session, order_id: int, monto: int, metodo: str, user: CurrentUser) -> dict:
    """RN-38 y RN-40: monto exacto; pago y comprobante en la misma transacción. Un reintento no duplica el cobro."""
    wo = ordenes.orden_para(db, order_id, user, lock=True)
    if db.scalar(select(Payment.id).where(Payment.work_order_id == wo.id)):
        raise HTTPException(409, "La orden ya tiene un pago registrado.")
    if wo.status != "PENDING_PAYMENT":
        raise HTTPException(409, "Solo se cobra una orden Pendiente de pago.")
    m = montos(db, wo)
    if monto != m["total"]:
        diferencia = monto - m["total"]
        raise HTTPException(409, f"El monto no coincide con el total ({m['total']:,}). "
                                 f"Diferencia: {diferencia:+,} pesos. El pago no se guardó.".replace(",", "."))
    seq = db.scalar(select(Sequence).where(Sequence.name == "RCP").with_for_update())
    if seq is None:
        raise HTTPException(500, "No fue posible generar el comprobante. Intente de nuevo.")
    seq.value += 1
    db.add(Payment(work_order_id=wo.id, amount=monto, method=metodo, created_at=ahora()))
    db.add(Receipt(work_order_id=wo.id, number=f"CMP-{seq.value:06d}", subtotal=m["subtotal"], vat=m["vat"],
                   total=m["total"], created_at=ahora()))
    ordenes.cambiar_estado(db, wo, "PAID", user)
    registrar(db, "payments", "PAYMENT", user.id, wo.id, {"amount": monto, "receipt": f"CMP-{seq.value:06d}"})
    db.commit()
    return _caja(db, wo)


def entregar(db: Session, order_id: int, user: CurrentUser) -> dict:
    wo = ordenes.orden_para(db, order_id, user, lock=True)
    if wo.status != "PAID":
        raise HTTPException(409, "No se puede entregar: la orden no está pagada.")
    ordenes.cambiar_estado(db, wo, "DELIVERED", user)
    if not db.scalar(select(Survey.id).where(Survey.work_order_id == wo.id)):
        db.add(Survey(work_order_id=wo.id, token=secrets.token_urlsafe(24)))
    db.commit()
    return _caja(db, wo)


def ticket(db: Session, order_id: int, codigo: str | None, user: CurrentUser) -> dict:
    """HU-17: el código solo sale si quien lo pide aún lo tiene y coincide; no se conserva."""
    wo = ordenes.orden_para(db, order_id, user)
    if codigo and sha256(codigo.strip().upper()) != wo.tracking_code_hash:
        raise HTTPException(409, "El código de seguimiento no corresponde a la orden.")
    v = db.get(Vehicle, wo.vehicle_id)
    assert v
    return {"taller": "Electrostock", "number": wo.number, "tracking_code": codigo.strip().upper() if codigo else None,
            "fecha_ingreso": wo.created_at, "tipo": ordenes.TIPOS[v.type], "marca": v.brand, "modelo": v.model,
            "serie_ultimos4": v.serial_number[-4:], "motivo": wo.intake_reason}


def _encuesta(db: Session, token: str, lock: bool = False) -> tuple[Survey, WorkOrder]:
    q = select(Survey).where(Survey.token == token[:64])
    encuesta = db.scalar(q.with_for_update() if lock else q)
    wo = db.get(WorkOrder, encuesta.work_order_id) if encuesta else None
    if encuesta is None or wo is None or wo.status != "DELIVERED":
        raise HTTPException(404, ENCUESTA_INVALIDA)
    return encuesta, wo


def ver_encuesta(db: Session, token: str) -> dict:
    encuesta, wo = _encuesta(db, token)
    return {"number": wo.number, "answered": encuesta.answered_at is not None}


def responder_encuesta(db: Session, token: str, score: int, comment: str | None) -> dict:
    encuesta, wo = _encuesta(db, token, lock=True)
    if encuesta.answered_at is not None:  # se conserva la primera respuesta (RN-41)
        raise HTTPException(409, "Esta encuesta ya fue respondida. ¡Gracias!")
    encuesta.score, encuesta.comment, encuesta.answered_at = score, (comment or "").strip() or None, ahora()
    db.commit()
    return {"number": wo.number, "answered": True}
