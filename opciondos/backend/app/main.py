"""API de la demo Electrostock: un router por módulo bajo /api."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.modulos.agenda import rutas as agenda
from app.modulos.agenda.tareas import start_scheduler
from app.modulos.auditoria import rutas as auditoria
from app.modulos.catalogo import rutas as catalogo
from app.modulos.clientes import rutas as clientes
from app.modulos.facturacion import rutas as facturacion
from app.modulos.identidad import rutas as identidad
from app.modulos.inventario import rutas as inventario
from app.modulos.ordenes import rutas as ordenes
from app.modulos.reportes import rutas as reportes
from app.semilla import seed_if_needed

SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin",
                    "Content-Security-Policy": "default-src 'self'"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    seed_if_needed()
    start_scheduler()
    yield


app = FastAPI(title="Electrostock demo", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.middleware("http")
async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    if not request.url.path.startswith("/api/docs"):
        response.headers.update(SECURITY_HEADERS)
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = sorted({str(e["loc"][-1]) for e in exc.errors()})
    return JSONResponse({"detail": "Por favor completa todos los campos obligatorios con un formato válido",
                         "fields": fields}, status_code=422)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (identidad, clientes, catalogo, agenda, inventario, ordenes, facturacion, reportes, auditoria):
    app.include_router(module.router, prefix="/api")
