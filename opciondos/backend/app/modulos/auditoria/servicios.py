"""Registro en la bitácora. Lo usan todos los módulos dentro de su misma transacción."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modulos.auditoria.modelos import AuditLog


def registrar(db: Session, entity: str, action: str, user_id: int | None = None,
              entity_id: int | None = None, detail: dict[str, Any] | None = None) -> None:
    db.add(AuditLog(entity=entity, entity_id=entity_id, action=action, user_id=user_id, detail=detail))


def consultar(db: Session, entity: str | None = None, action: str | None = None,
              limit: int = 200) -> list[dict[str, Any]]:
    """HU-20: lectura de la bitácora, la más reciente primero."""
    from app.modulos.identidad.modelos import User

    query = select(AuditLog, User.full_name).outerjoin(User, User.id == AuditLog.user_id)
    if entity:
        query = query.where(AuditLog.entity == entity)
    if action:
        query = query.where(AuditLog.action == action)
    rows = db.execute(query.order_by(AuditLog.id.desc()).limit(limit))
    return [{"id": a.id, "entity": a.entity, "entity_id": a.entity_id, "action": a.action, "user_id": a.user_id,
             "user_name": name, "detail": a.detail, "created_at": a.created_at} for a, name in rows]


def opciones(db: Session) -> dict[str, list[str]]:
    return {"entidades": list(db.scalars(select(AuditLog.entity).distinct().order_by(AuditLog.entity))),
            "acciones": list(db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)))}
