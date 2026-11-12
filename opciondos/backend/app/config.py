"""Configuración por variables de entorno."""

import os
from zoneinfo import ZoneInfo


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


DB_URL = (
    f"mysql+pymysql://{_env('DB_USER', 'electrostock')}:{_env('DB_PASSWORD', 'electrostock')}"
    f"@{_env('DB_HOST', '127.0.0.1')}:{_env('DB_PORT', '3306')}/{_env('DB_NAME', 'electrostock')}?charset=utf8mb4"
)
JWT_SECRET = _env("JWT_SECRET", "")
if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET debe tener al menos 32 caracteres")
ACCESS_MINUTES = int(_env("ACCESS_MINUTES", "15"))
REFRESH_HOURS = int(_env("REFRESH_HOURS", "8"))
COOKIE_SECURE = _env("COOKIE_SECURE", "false").lower() == "true"
RESET_SEED = _env("RESET_SEED", "false").lower() == "true"
SEED_PATH = _env("SEED_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "seed.json"))
TZ = ZoneInfo("America/Bogota")

# Parámetros de negocio (IEEE 830, RN): bloqueo 5 min, tolerancia 15 min, ventana de cambio 60 min.
HOLD_MINUTES = 5
NO_SHOW_MINUTES = 15
CHANGE_WINDOW_MINUTES = 60
OPEN_HOUR, LAST_SLOT_HOUR = 8, 17  # franjas de 1 h de 08:00 a 18:00, lunes a sábado
VAT_RATE = 0.19
