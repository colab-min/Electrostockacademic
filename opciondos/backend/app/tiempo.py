"""Hora local del taller (America/Bogota). La base guarda hora local sin zona en esta demo."""

from datetime import datetime

from app import config


def ahora() -> datetime:
    return datetime.now(config.TZ).replace(tzinfo=None, microsecond=0)
