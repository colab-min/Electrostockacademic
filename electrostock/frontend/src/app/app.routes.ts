import { Routes } from '@angular/router';

import { authGuard } from './core/auth.guard';
import { LoginPageComponent } from './components/login-page/login-page.component';
import { RegisterPageComponent } from './components/register-page/register-page.component';
import { WorkspacePageComponent } from './components/workspace-page/workspace-page.component';

const workspace = (page: string, roles?: string[]) => ({
  component: WorkspacePageComponent,
  canActivate: [authGuard],
  data: { page, roles },
});

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'ingresar' },
  { path: 'ingresar', component: LoginPageComponent },
  { path: 'registro', component: RegisterPageComponent },
  { path: 'encuesta/:token', component: WorkspacePageComponent, data: { page: 'survey' } },
  { path: 'seguimiento/:code', component: WorkspacePageComponent, data: { page: 'tracking' } },
  { path: 'cliente/citas', ...workspace('appointments', ['CUSTOMER']) },
  { path: 'cliente/agendar', ...workspace('appointments', ['CUSTOMER']) },
  { path: 'cliente/citas/:id/reprogramar', ...workspace('appointments', ['CUSTOMER']) },
  { path: 'cliente/vehiculos/nuevo', ...workspace('vehicles', ['CUSTOMER']) },
  { path: 'cliente/vehiculos/:id/historial', ...workspace('vehicles', ['CUSTOMER']) },
  { path: 'recepcion/agenda', ...workspace('appointments', ['RECEPTIONIST', 'ADMIN']) },
  { path: 'recepcion/ingreso', ...workspace('workOrders', ['RECEPTIONIST', 'ADMIN']) },
  { path: 'recepcion/ordenes/nueva', ...workspace('workOrders', ['RECEPTIONIST', 'ADMIN']) },
  { path: 'recepcion/clientes/nuevo', ...workspace('vehicles', ['RECEPTIONIST', 'ADMIN']) },
  { path: 'recepcion/ordenes/:id/cobro', ...workspace('workOrders', ['RECEPTIONIST', 'ADMIN']) },
  { path: 'taller/bahia', ...workspace('workOrders', ['MECHANIC']) },
  { path: 'taller/ordenes/:id', ...workspace('workOrders', ['MECHANIC']) },
  { path: 'taller/vehiculos/expediente', ...workspace('vehicles', ['MECHANIC', 'RECEPTIONIST', 'ADMIN']) },
  { path: 'admin/indicadores', ...workspace('reports', ['ADMIN']) },
  { path: 'admin/asignacion', ...workspace('workOrders', ['ADMIN']) },
  { path: 'admin/inventario', ...workspace('inventory', ['ADMIN']) },
  { path: 'admin/clientes', ...workspace('customers', ['ADMIN']) },
  { path: 'admin/vehiculos', ...workspace('vehicles', ['ADMIN']) },
  { path: 'admin/catalogo', ...workspace('catalog', ['ADMIN']) },
  { path: 'admin/usuarios', ...workspace('users', ['ADMIN']) },
  { path: 'admin/bitacora', ...workspace('reports', ['ADMIN']) },
  { path: 'perfil/cambiar-contrasena', ...workspace('dashboard', ['CUSTOMER', 'RECEPTIONIST', 'MECHANIC', 'ADMIN']) },
  { path: '**', redirectTo: 'ingresar' },
];
