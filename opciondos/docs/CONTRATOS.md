# Contratos de trabajo de la demo

Documento interno para construir la demo en paralelo. Todo bajo `/api`. Las respuestas son JSON; los errores, `HTTPException(status, "mensaje en español")`, que llega como `{"detail": "..."}`. Un 422 de validación de Pydantic llega como `{"detail": "Por favor completa todos los campos obligatorios con un formato válido", "fields": [...]}`.

## Reglas comunes

**Backend** (`backend/app/`)
- Cada módulo tiene `modelos.py` (ya escritos: **no los cambies**; si te falta una columna, anótalo en tu informe), `esquemas.py` (Pydantic), `servicios.py` (lógica) y `rutas.py` (FastAPI, `router` ya incluido en `main.py` con prefijo `/api`).
- Autorización en cada ruta no pública: `user: CurrentUser = Depends(require_roles("ADMIN", ...))` de `app.seguridad`. Sesión de BD: `db: Session = Depends(get_db)` de `app.db`.
- Hora local: `from app.tiempo import ahora`. Parámetros de negocio en `app.config` (HOLD_MINUTES=5, NO_SHOW_MINUTES=15, CHANGE_WINDOW_MINUTES=60, OPEN_HOUR=8, LAST_SLOT_HOUR=17, VAT_RATE=0.19).
- Bitácora: `from app.modulos.auditoria.servicios import registrar` dentro de la misma transacción (cambios de estado de citas y órdenes, asignaciones, movimientos de inventario, gestión de usuarios).
- Reservas de repuestos: `app.modulos.inventario.servicios` (`reservar_para_cita`, `liberar`, `extender`, `transferir_a_orden`, `repuestos_requeridos`). Concurrencia: bloquea primero las franjas (`select(Slot)...with_for_update()` ordenado por id) y después los repuestos.
- Tareas periódicas: decora una función `fn(db)` con `@registrar_tarea("nombre")` de `app.modulos.agenda.tareas` en tu `servicios.py`; corre al arrancar y cada 60 s. Usa `with_for_update(skip_locked=True)` y que sea idempotente.
- Nunca borres físicamente órdenes, citas, movimientos ni bitácora: se cambian de estado o se desactivan.
- Pruebas: `backend/tests/test_<modulo>.py` con `fastapi.testclient.TestClient(app)`. Cada agente usa **su propia base**: `DB_NAME=electrostock_<a|b|c>`, `DB_PORT=3326`, `DB_USER=electrostock`, `DB_PASSWORD=demo-app-password`, `JWT_SECRET=demo-only-secret-change-me-0123456789abcdef`, `RESET_SEED=true` (el arranque recarga la semilla). Intérprete: `backend/.venv/bin/python`.

**Frontend** (`frontend/src/app/`)
- Tus pantallas ya existen como esqueleto en `vistas/<portal>/<vista>/` con `.ts`, `.html` y `.css`: reemplázalas. Sin plantillas ni estilos en línea.
- Usa los componentes de `componentes/` (lee su `.ts` para ver las entradas): `app-boton`, `app-campo`, `app-insignia-estado`, `app-tarjeta`, `app-aviso`, `app-estado-vacio`, `app-dialogo-confirmacion`, `app-calendario-mes`, `app-franja-horaria`, `app-linea-tiempo`, `app-buscador-vehiculo`, `app-tabla-datos`, `app-espacio-fotos`.
- **No edites** `componentes/`, `core/`, `app.routes.ts`, `app.config.ts`, `styles*`. Si necesitas un componente nuevo que usarán 2 o más vistas, créalo en `componentes/<nombre>/` (nombre nuevo) y avísalo en tu informe; si lo usa una sola vista, va dentro de la carpeta de la vista.
- Colores solo con las variables de `styles/tokens.css`. El caqui (`--color-registro`) nunca como color de texto.
- HTTP con `HttpClient` directo a `/api/...` (el interceptor agrega el token). Errores: `mensajeError(err)` y `camposConError(err)` de `core/errores`. Formatos: `core/formato` (pesos, fechas). Sesión: `SesionService` de `core/sesion.service`.
- Estados de cada vista (IS-4 7.7): carga (botón en "Procesando…"), vacío (`app-estado-vacio`), error (`app-aviso tipo="error"`). Tuteo en vistas de cliente y públicas; usted en recepción, taller y admin.
- Verifica con `cd frontend && npx ng build --output-path /tmp/ng-<a|b|c>`. Responsive: web y celular.

## Endpoints y dueños

**A: agenda, inventario y catálogo**
- `GET /catalogo/servicios` (todos los roles): `[{id, code, name, labor_price, duration_min, active, repuestos: [{part_id, sku, name, quantity, available}]}]`; `?todos=true` incluye inactivos (ADMIN).
- `POST /catalogo/servicios`, `PATCH /catalogo/servicios/{id}`, `PUT /catalogo/servicios/{id}/repuestos` `[{part_id, quantity}]` (ADMIN).
- `GET /catalogo/fallas` (RECEPTIONIST, ADMIN): `[{id, name, priority, estimated_minutes}]`.
- `GET /agenda/disponibilidad?service_id=&mes=AAAA-MM` y `GET /agenda/franjas?service_id=&fecha=AAAA-MM-DD` (CUSTOMER).
- `POST /agenda/citas`, `POST /agenda/citas/{id}/confirmar|cancelar|reprogramar`, `GET /agenda/citas/mias` (CUSTOMER).
- `GET /agenda/calendario?fecha=` y `POST /agenda/franjas/{id}/bloqueo` (RECEPTIONIST, ADMIN).
- `GET /inventario/repuestos` (ADMIN; MECHANIC lectura), `POST /inventario/repuestos`, `PATCH /inventario/repuestos/{id}`, `POST /inventario/movimientos`, `GET /inventario/movimientos` (ADMIN).

**B: órdenes, taller, seguimiento y facturación**
- `GET /ordenes/citas-del-dia?q=` (RECEPTIONIST, ADMIN): citas vigentes de hoy por código, serie o placa.
- `POST /ordenes` `{appointment_id}` y `POST /ordenes/ingreso` `{vehicle_id, fault_type_id, service_id, intake_reason}` (RECEPTIONIST, ADMIN): devuelven `{id, number, tracking_code, ...}` (el código en claro solo aquí).
- `GET /ordenes/cola`, `POST /ordenes/{id}/cancelar` (RECEPTIONIST, ADMIN).
- `GET /ordenes/mias`, `GET /ordenes/{id}`, `GET /ordenes/{id}/transiciones`, `POST /ordenes/{id}/estado` `{to_status, version, reason?}`, `PATCH /ordenes/{id}/diagnostico`, repuestos y servicios adicionales (MECHANIC asignado).
- `GET /ordenes?estado=`, `POST /ordenes/{id}/asignacion` `{mechanic_id}` (ADMIN). Mecánicos: `GET /usuarios/mecanicos` (ya existe).
- `GET /seguimiento/{codigo}` (público, 30 consultas/min por IP): `{tipo, modelo, estado, estado_publico, linea_tiempo: [{titulo, fecha}], entrega_estimada}`; nada personal ni costos.
- `GET /facturacion/ordenes?estado=`, `POST /facturacion/ordenes/{id}/liquidar|pagos|entregar`, `GET /facturacion/ordenes/{id}/ticket` (RECEPTIONIST, ADMIN). `GET|POST /encuestas/{token}` (público).

**C: clientes, expediente, reportes, auditoría y usuarios**
- `GET /clientes/vehiculos?q=` (RECEPTIONIST, ADMIN, MECHANIC): `[{id, type, serial_number, plate, brand, model, nominal_voltage_v, customer: {id, full_name, document_type, document_number}}]` por serie, placa o documento.
- `GET /clientes/vehiculos/{serie}/expediente` (MECHANIC, RECEPTIONIST, ADMIN) y `POST /clientes/vehiculos/{id}/notas` (MECHANIC, HTML sanitizado con `nh3`).
- `GET /clientes?document_type=&document_number=`, `POST /clientes` (cliente nuevo + vehículo + casilla), `PATCH /clientes/{id}` (teléfono y correo) (RECEPTIONIST, ADMIN).
- `POST /clientes/vehiculos` (CUSTOMER: el propio; RECEPTIONIST/ADMIN: con `customer_id`).
- `GET /clientes/mis-vehiculos` (CUSTOMER): `[{id, type, serial_number, plate, brand, model, nominal_voltage_v}]`; `GET /clientes/mis-vehiculos/{id}/historial` (CUSTOMER).
- `GET /reportes/resumen?desde=&hasta=` (ADMIN). `GET /auditoria/bitacora?entidad=&accion=` (ADMIN).
- Usuarios: el backend ya existe (`GET|POST /usuarios`, `PATCH /usuarios/{id}`); falta la vista.
