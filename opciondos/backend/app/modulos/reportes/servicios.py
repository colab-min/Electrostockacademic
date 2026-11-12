"""HU-14: indicadores por rango de fechas. Solo lectura (ADR-37)."""

from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modulos.agenda.modelos import Slot
from app.modulos.facturacion.modelos import Payment, Survey
from app.modulos.inventario.modelos import Part
from app.modulos.ordenes.modelos import WorkOrder, WorkOrderPart


def summary(db: Session, since: date, until: date) -> dict[str, Any]:
    if since > until:
        raise HTTPException(422, "La fecha inicial no puede ser posterior a la final.")
    start, end = datetime.combine(since, time()), datetime.combine(until + timedelta(days=1), time())

    revenue = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0))
                        .where(Payment.created_at >= start, Payment.created_at < end))
    by_status = db.execute(select(WorkOrder.status, func.count()).where(WorkOrder.created_at >= start,
                                                                        WorkOrder.created_at < end)
                           .group_by(WorkOrder.status).order_by(func.count().desc()))
    booked, capacity = db.execute(select(func.coalesce(func.sum(Slot.booked_count), 0),
                                         func.coalesce(func.sum(Slot.capacity), 0))
                                  .where(Slot.slot_date >= since, Slot.slot_date <= until,
                                         Slot.blocked.is_(False))).one()
    parts = db.execute(select(Part.sku, Part.name, func.sum(WorkOrderPart.quantity).label("qty"))
                       .join(WorkOrderPart, WorkOrderPart.part_id == Part.id)
                       .join(WorkOrder, WorkOrder.id == WorkOrderPart.work_order_id)
                       .where(WorkOrderPart.status == "INSTALLED", WorkOrder.created_at >= start,
                              WorkOrder.created_at < end)
                       .group_by(Part.id, Part.sku, Part.name).order_by(func.sum(WorkOrderPart.quantity).desc())
                       .limit(10))
    avg_score, answers = db.execute(select(func.avg(Survey.score), func.count(Survey.score))
                                    .where(Survey.answered_at >= start, Survey.answered_at < end)).one()
    return {
        "desde": since, "hasta": until,
        "ingresos": int(revenue),
        "ordenes_por_estado": [{"estado": s, "cantidad": n} for s, n in by_status],
        "ocupacion": {"reservadas": int(booked), "capacidad": int(capacity),
                      "porcentaje": round(100 * int(booked) / int(capacity)) if capacity else 0},
        "repuestos": [{"sku": s, "name": n, "cantidad": int(q)} for s, n, q in parts],
        "satisfaccion": {"promedio": round(float(avg_score), 1) if avg_score is not None else None,
                         "respuestas": answers},
    }
