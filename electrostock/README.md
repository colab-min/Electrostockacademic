# Electrostock

Aplicación para operar un taller de vehículos eléctricos. El repositorio incluye una SPA Angular, una API FastAPI, persistencia MySQL 8.4 y datos iniciales de demostración.

## Requisitos

- Docker Engine con Docker Compose
- Navegador moderno

## Arranque local

```bash
cp .env.example .env
# Cambia las contraseñas y JWT_SECRET antes de exponer el servicio fuera de tu equipo.
docker compose up --build
```

- Web: <http://127.0.0.1:4200>
- API y OpenAPI: <http://127.0.0.1:8000/api/v1/docs>
- Salud: <http://127.0.0.1:8000/api/v1/health>
- phpMyAdmin opcional: `docker compose --profile herramientas up -d phpmyadmin`, <http://127.0.0.1:8080>

Si los puertos predeterminados están ocupados, configura `FRONTEND_PORT`, `API_HOST_PORT` y `MYSQL_PORT` en `.env`. En Compose, la SPA envía las llamadas `/api/` al backend mediante Nginx.

El esquema se crea con Alembic y los datos de demostración se cargan desde `fixtures/test-data.json`. Para detener los servicios conserva los datos con `docker compose down`; `docker compose down -v` elimina el volumen MySQL.

## Cuentas de demostración

| Rol | Usuario | Contraseña |
|---|---|---|
| Administrador | `admin@electrostock.test` | `Admin2026!` |
| Recepción | `recepcion@electrostock.test` | `Recep2026!` |
| Recepción temporal | `recepcion2@electrostock.test` | `Temporal2026!` |
| Mecánico | `mecanico1@electrostock.test` | `Meca2026!a` |
| Cliente | `cliente1@electrostock.test` | `Cliente2026!` |

Son cuentas locales de prueba. No se deben reutilizar en producción.

## Desarrollo y pruebas

API:

```bash
cd backend
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
```

La API usa SQLite local por defecto para desarrollo y pruebas. Para conectarla a MySQL, establece `DATABASE_URL=mysql+pymysql://usuario:contraseña@127.0.0.1:3306/electrostock`.

Frontend:

```bash
cd frontend
npm ci
npm start -- --host 127.0.0.1
```

En otra terminal, desde `backend/`, ejecuta `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.

## Alcance de la demo

La demo funcional cubre registro e inicio de sesión, clientes y vehículos, expediente técnico, catálogo y repuestos por servicio, reserva de inventario, agenda y reprogramación, ingreso sin cita y cola, liberación automática de reservas, creación y asignación de órdenes, avance del estado, cobro con recibo, entrega con encuesta pública e indicadores administrativos. La interfaz organiza los portales de administración, recepción, mecánica y cliente con el lenguaje visual de los wireframes. La semilla es aditiva e idempotente: además de los catálogos crea citas y órdenes representativas para probar la cola, la bahía mecánica, el historial y el seguimiento `K7M2QX9P4T`.

En desarrollo local, el backend usa SQLite en `backend/electrostock.db`; en Docker Compose usa MySQL 8.4 con el volumen `mysql_data`. Los cambios de la demo se guardan en la base de datos configurada y sobreviven al reinicio del servicio. Para recargar el fixture desde cero, usa una base vacía (por ejemplo, `docker compose down -v`) y vuelve a arrancar Compose.

Funciones adicionales de la especificación general (por ejemplo, reintentos de notificaciones, PDF/QR y modo sin conexión) están fuera del alcance de esta demo y no se presentan como terminadas.
