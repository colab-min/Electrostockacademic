# Electrostock: demo

Demostración funcional de Electrostock, la plataforma de un taller de vehículos eléctricos livianos: una cita solo se confirma con cupo y repuesto reservados, el taller la convierte en orden, el mecánico la avanza y el cliente lo ve en su seguimiento.

Es una demo para presentar, construida sobre datos semilla; no es el producto final. La carpeta `electrostock/` es otro proyecto y no forma parte de esta demo.

## Levantar la demo

Requisito: Docker con Compose v2.

```bash
docker compose up --build
```

| Servicio | URL |
|---|---|
| Aplicación | http://127.0.0.1:4220 |
| API (documentación) | http://127.0.0.1:8020/api/docs |
| phpMyAdmin (opcional) | `docker compose --profile tools up -d phpmyadmin` → http://127.0.0.1:8030 |

- La primera vez, el backend crea las tablas y carga `fixtures/seed.json`. Las fechas de la semilla son relativas al día en que se carga.
- **Antes de presentar, recarga la semilla** para que las citas y órdenes de "hoy" coincidan con la fecha: `RESET_SEED=true docker compose up -d backend` (o borra todo con `docker compose down -v`).
- Puertos y secretos se cambian copiando `.env.example` a `.env`.

## Usuarios de prueba

| Rol | Correo | Contraseña |
|---|---|---|
| Cliente | cliente1@electrostock.test | Cliente2026! |
| Secretaria | recepcion@electrostock.test | Recep2026! |
| Mecánico | mecanico2@electrostock.test | Meca2026!b |
| Administrador | admin@electrostock.test | Admin2026! |

Otros: `mecanico1@electrostock.test` / `Meca2026!a`; `cliente2@` y `cliente3@electrostock.test` / `Cliente2026!`; `recepcion2@electrostock.test` / `Temporal2026!` (contraseña temporal: pide cambiarla al entrar); `mecanico3@electrostock.test` está desactivado. Son credenciales de demostración, solo para uso local.

## Guion de demostración (5 minutos)

Prepara dos ventanas del navegador: una para el taller y otra (o el celular) para el seguimiento público. Recarga la semilla en horario hábil (antes de las 17:00), porque la cita del día que se convierte en orden se ubica en la siguiente franja libre de hoy.

1. **Login y seguridad (0:00 a 0:40).** En http://127.0.0.1:4220 entra con una contraseña errada: "Credenciales inválidas, por favor intenta de nuevo". Comenta que al quinto intento fallido se bloquea el siguiente por 15 minutos y que las contraseñas se guardan con Argon2id.
2. **Agendar con reserva (0:40 a 2:00).** Entra como cliente (`cliente1`). "Agendar": vehículo SC-48-0001, servicio "Cambio de batería 48V". Muestra que el paso 1 indica el repuesto y su disponible. Elige mañana, una hora libre y llega al resumen: el contador de 5 minutos y "Batería litio 48V 15Ah x1 - apartada". Confirma y se obtiene el código CITA-AAAAMMDD-NNNN con la hora límite para cancelar. Vuelve a intentar con "Cambio de batería 60V": se rechaza porque no hay repuesto disponible. La cita aparece en "Mis citas", donde se puede reprogramar o cancelar.
3. **Recepción crea la orden (2:00 a 2:50).** Sal ("Salir") y entra como secretaria (`recepcion`). En "Órdenes" busca BI-48-0010 (la cita de hoy) y crea la orden: recibe el número OT-000011 y el código de seguimiento, que se muestra una sola vez. Escribe en la barra `/admin/usuarios`: redirige con "No tiene permisos para esta sección".
4. **Seguimiento público (2:50 a 3:15).** En la otra ventana, sin iniciar sesión, abre "Seguimiento" con el código `M8E3K6T4ZD` (OT-000006): estado "Recibido", línea de tiempo y entrega estimada, sin datos personales ni costos.
5. **El mecánico avanza la orden (3:15 a 4:15).** Entra como mecánico (`mecanico2`). En el panel de bahía, OT-000006 está "Asignada": avánzala a "En diagnóstico". En menos de 3 segundos el seguimiento público cambia solo. Abre el detalle para mostrar las transiciones válidas, el diagnóstico y el historial.
6. **Cierre (4:15 a 5:00).** Como administrador (`admin`), muestra "Indicadores", la "Bitácora" (el acceso denegado del paso 3 y los cambios de estado quedan registrados y no se pueden borrar) y el inventario con las alertas de stock. Termina con "Salir".

Otros recorridos disponibles: ingreso sin cita con cola por prioridad (Recepción → Ingreso), caja con OT-000010 en pendiente de pago (cobro, comprobante, entrega y encuesta), expediente técnico de SC-48-0001 con notas (Expediente), registro de cliente y vehículo, asignación de mecánicos, catálogo con repuestos por servicio y la agenda con semáforo y bloqueo de franjas.

## Cobertura de las 30 historias

| Portal | Vistas | HU |
|---|---|---|
| Público | Iniciar sesión, Crear cuenta, Seguimiento | HU-21, HU-15 (contraseña temporal), HU-07 |
| Cliente | Mis citas y vehículos, Agendar (4 pasos), Reprogramar, Registrar vehículo, Historial, Encuesta | HU-01, HU-19, HU-11, HU-22, HU-30, HU-16 |
| Secretaria | Agenda y capacidad, Ingreso sin cita, Registrar cliente, Crear y cancelar orden, Caja | HU-02, HU-12, HU-03, HU-04, HU-22, HU-23, HU-17, HU-13 |
| Mecánico | Panel de bahía, Detalle de orden, Expediente | HU-05, HU-09, HU-25, HU-06 |
| Administrador | Indicadores, Asignación, Inventario, Catálogo, Usuarios, Bitácora | HU-14, HU-24, HU-08, HU-27, HU-29, HU-18, HU-26, HU-15, HU-20 |
| Sin vista propia | Guardias y validación de rol; tareas cada 60 s | HU-10, HU-28, HU-12 |

Las 12 del POC (HU-01, 03, 05, 06, 07, 11, 19, 21, 22, 23, 26 y 28) tienen su lógica completa; las demás funcionan de forma sencilla sobre la semilla.

## Seguridad que se ve en la demo

- Contraseñas con Argon2id (m 19 MiB, t 2, p 1); nunca en texto plano.
- JWT de acceso de 15 minutos en memoria y renovación rotativa en cookie HttpOnly; "Salir" la revoca.
- Cada rol ve solo sus pantallas: guardia de rutas en Angular y validación del rol en cada ruta del backend. Una ruta sin permiso redirige con "No tiene permisos para esta sección" y el intento queda en la bitácora.
- "Credenciales inválidas, por favor intenta de nuevo" para contraseña incorrecta o cuenta desactivada; 5 intentos fallidos en 15 minutos bloquean el siguiente.
- Consultas del ORM (parametrizadas), validación de entradas con Pydantic, cabeceras de seguridad y CSP con nonce, notas técnicas sanitizadas, bitácora de solo inserción (un trigger de MySQL rechaza UPDATE y DELETE).

## Estructura

```
backend/app/modulos/<modulo>/   modelos.py, esquemas.py, servicios.py, rutas.py
frontend/src/app/componentes/   componentes reutilizables (usados en 2 o más vistas)
frontend/src/app/vistas/        pantallas por portal y módulo (.ts, .html, .css)
frontend/src/styles/tokens.css  paleta Riso wa-iro y tipografías
fixtures/seed.json              datos semilla
```

## Pruebas

```bash
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
# con el MySQL de la demo levantado; usa una base aparte porque recarga la semilla
DB_NAME=electrostock_d DB_PORT=3326 DB_USER=electrostock DB_PASSWORD=demo-app-password \
JWT_SECRET=demo-only-secret-change-me-0123456789abcdef RESET_SEED=true .venv/bin/python -m pytest -q
```

## Decisiones simples tomadas ante ambigüedades

- La base guarda la hora local del taller (America/Bogota) sin zona horaria.
- El esquema lo crea SQLAlchemy al arrancar (sin migraciones) y la semilla se carga si la base está vacía.
- El "tiempo real" del panel de bahía y del seguimiento es un sondeo cada 3 segundos en lugar de SSE.
- El límite de intentos de login vive en memoria del proceso (una sola instancia).
- Agenda: el código de cita usa el id de la cita como NNNN; la capacidad de las franjas es fija en 3 (no hay tabla de bahías); el contador de 5 minutos corre en el navegador y el servidor valida el vencimiento; "Cancelar" en el paso 4 vuelve a elegir hora; la agenda de recepción se actualiza con un botón.
- Recordatorios (HU-12): se generan para las citas de las próximas 24 horas y el envío es simulado (pasa a "Enviada" en el mismo paso).
- Inventario: la alerta se activa con disponible igual o menor al umbral; los ajustes se guardan como diferencia con signo.
- Ingreso sin cita: se ubica desde la siguiente franja que empieza a partir de la hora actual; la cola se reordena por prioridad y llegada, y una falla de menos de 15 minutos adelanta a las de prioridad igual o menor. La cola se ubica sola cuando se cancela una orden o al cierre del día.
- Facturación: el comprobante se emite junto con el pago; el ticket se imprime con la impresión del navegador (80 mm), sin QR.
- Clientes: la búsqueda de vehículos es por coincidencia exacta de serie, placa o documento; marca, modelo, año, voltaje y capacidad son obligatorios; el editor de notas permite negrita y listas y se sanitiza con `nh3`.
- Reportes: por defecto cubren los últimos 30 días; no hay librería de gráficos (cifras y tablas).
