"""Programador de tareas periódicas (HU-28, HU-12, HU-03 cola).

Cada módulo registra sus tareas con `registrar_tarea` al importarse; `start_scheduler` las corre al arrancar
y luego cada 60 s, cada una en su propia sesión. Deben ser idempotentes (usar SELECT ... FOR UPDATE SKIP LOCKED).
"""

import logging
import threading
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.db import SessionLocal

log = logging.getLogger("tareas")
INTERVALO_S = 60
_tareas: list[tuple[str, Callable[[Session], None]]] = []
_iniciado = False


def registrar_tarea(nombre: str) -> Callable[[Callable[[Session], None]], Callable[[Session], None]]:
    def decorador(fn: Callable[[Session], None]) -> Callable[[Session], None]:
        _tareas.append((nombre, fn))
        return fn

    return decorador


def correr_todas() -> None:
    for nombre, fn in list(_tareas):
        try:
            with SessionLocal() as db:
                fn(db)
                db.commit()
        except Exception:
            log.exception("La tarea %s falló", nombre)


def start_scheduler() -> None:
    global _iniciado
    if _iniciado:
        return
    _iniciado = True
    correr_todas()  # al arrancar se libera lo vencido (HU-28 esc. 5)
    stop = threading.Event()

    def bucle() -> None:
        while not stop.wait(INTERVALO_S):
            correr_todas()

    threading.Thread(target=bucle, name="tareas", daemon=True).start()
