import { Routes } from '@angular/router';
import { guardiaRol } from './core/guardia-rol';

const CLIENTE = [guardiaRol('CUSTOMER')];
const RECEPCION = [guardiaRol('RECEPTIONIST', 'ADMIN')];
const MECANICO = [guardiaRol('MECHANIC')];
const EXPEDIENTE = [guardiaRol('MECHANIC', 'RECEPTIONIST', 'ADMIN')];
const ADMIN = [guardiaRol('ADMIN')];

/** Rutas con carga diferida y guardia por rol (IS-4 sección 3, SAD 5.2.4). */
export const routes: Routes = [
  { path: 'ingresar', loadComponent: () => import('./vistas/publico/ingresar/ingresar').then((m) => m.VistaIngresar) },
  { path: 'registro', loadComponent: () => import('./vistas/publico/crear-cuenta/crear-cuenta').then((m) => m.VistaCrearCuenta) },
  { path: 'seguimiento', loadComponent: () => import('./vistas/publico/seguimiento/seguimiento').then((m) => m.VistaSeguimiento) },
  { path: 'seguimiento/:codigo', loadComponent: () => import('./vistas/publico/seguimiento/seguimiento').then((m) => m.VistaSeguimiento) },
  { path: 'encuesta/:token', loadComponent: () => import('./vistas/cliente/encuesta/encuesta').then((m) => m.VistaEncuesta) },

  { path: 'cliente/citas', canMatch: CLIENTE, loadComponent: () => import('./vistas/cliente/mis-citas/mis-citas').then((m) => m.VistaMisCitas) },
  { path: 'cliente/agendar', canMatch: CLIENTE, loadComponent: () => import('./vistas/cliente/agendar/agendar').then((m) => m.VistaAgendar) },
  { path: 'cliente/citas/:id/reprogramar', canMatch: CLIENTE, loadComponent: () => import('./vistas/cliente/reprogramar/reprogramar').then((m) => m.VistaReprogramar) },
  { path: 'cliente/vehiculos/nuevo', canMatch: CLIENTE, loadComponent: () => import('./vistas/cliente/registrar-vehiculo/registrar-vehiculo').then((m) => m.VistaRegistrarVehiculo) },
  { path: 'cliente/vehiculos/:id/historial', canMatch: CLIENTE, loadComponent: () => import('./vistas/cliente/historial/historial').then((m) => m.VistaHistorial) },

  { path: 'recepcion/agenda', canMatch: RECEPCION, loadComponent: () => import('./vistas/recepcion/agenda-capacidad/agenda-capacidad').then((m) => m.VistaAgendaCapacidad) },
  { path: 'recepcion/ingreso', canMatch: RECEPCION, loadComponent: () => import('./vistas/recepcion/ingreso-sin-cita/ingreso-sin-cita').then((m) => m.VistaIngresoSinCita) },
  { path: 'recepcion/clientes/nuevo', canMatch: RECEPCION, loadComponent: () => import('./vistas/recepcion/registrar-cliente/registrar-cliente').then((m) => m.VistaRegistrarCliente) },
  { path: 'recepcion/ordenes/nueva', canMatch: RECEPCION, loadComponent: () => import('./vistas/recepcion/crear-orden/crear-orden').then((m) => m.VistaCrearOrden) },
  { path: 'recepcion/caja', canMatch: RECEPCION, loadComponent: () => import('./vistas/recepcion/caja/caja').then((m) => m.VistaCaja) },

  { path: 'taller/bahia', canMatch: MECANICO, loadComponent: () => import('./vistas/taller/panel-bahia/panel-bahia').then((m) => m.VistaPanelBahia) },
  { path: 'taller/ordenes/:id', canMatch: MECANICO, loadComponent: () => import('./vistas/taller/detalle-orden/detalle-orden').then((m) => m.VistaDetalleOrden) },
  { path: 'taller/vehiculos', canMatch: EXPEDIENTE, loadComponent: () => import('./vistas/taller/expediente/expediente').then((m) => m.VistaExpediente) },
  { path: 'taller/vehiculos/:serie', canMatch: EXPEDIENTE, loadComponent: () => import('./vistas/taller/expediente/expediente').then((m) => m.VistaExpediente) },

  { path: 'admin/indicadores', canMatch: ADMIN, loadComponent: () => import('./vistas/admin/indicadores/indicadores').then((m) => m.VistaIndicadores) },
  { path: 'admin/asignacion', canMatch: ADMIN, loadComponent: () => import('./vistas/admin/asignacion/asignacion').then((m) => m.VistaAsignacion) },
  { path: 'admin/inventario', canMatch: ADMIN, loadComponent: () => import('./vistas/admin/inventario/inventario').then((m) => m.VistaInventario) },
  { path: 'admin/catalogo', canMatch: ADMIN, loadComponent: () => import('./vistas/admin/catalogo/catalogo').then((m) => m.VistaCatalogo) },
  { path: 'admin/usuarios', canMatch: ADMIN, loadComponent: () => import('./vistas/admin/usuarios/usuarios').then((m) => m.VistaUsuarios) },
  { path: 'admin/bitacora', canMatch: ADMIN, loadComponent: () => import('./vistas/admin/bitacora/bitacora').then((m) => m.VistaBitacora) },

  { path: '', pathMatch: 'full', redirectTo: 'ingresar' },
  { path: '**', redirectTo: 'ingresar' },
];
