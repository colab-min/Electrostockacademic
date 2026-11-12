from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import SessionLocal
from app.routers import router
from app.seed import seed_database
from app.tasks import run_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.create_schema:
        alembic_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        alembic_config.set_main_option(
            "sqlalchemy.url",
            settings.database_url.replace("%", "%%"),
        )
        command.upgrade(alembic_config, "head")
    project_root = Path(__file__).resolve().parents[2]
    fixture_path = project_root / "fixtures" / "test-data.json"
    if not fixture_path.exists():
        fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "test-data.json"
    with SessionLocal() as db:
        seed_database(db, fixture_path)
    scheduler_task = None
    if settings.scheduler_enabled:
        import asyncio

        scheduler_task = asyncio.create_task(run_scheduler())
    yield
    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Electrostock API",
    description="API para clientes, agenda, inventario, órdenes y facturación del taller.",
    version="0.1.0",
    lifespan=lifespan,
)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
app.include_router(router)
