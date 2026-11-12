import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { Rol, SesionService } from '../../core/sesion.service';
import { Icono } from '../icono/icono';

const MENU: Record<Rol, { ruta: string; texto: string }[]> = {
  CUSTOMER: [{ ruta: '/cliente/citas', texto: 'Mis citas' }, { ruta: '/cliente/agendar', texto: 'Agendar' }],
  RECEPTIONIST: [
    { ruta: '/recepcion/agenda', texto: 'Agenda' }, { ruta: '/recepcion/ingreso', texto: 'Ingreso' },
    { ruta: '/recepcion/ordenes/nueva', texto: 'Órdenes' }, { ruta: '/recepcion/caja', texto: 'Caja' },
    { ruta: '/recepcion/clientes/nuevo', texto: 'Clientes' },
  ],
  MECHANIC: [{ ruta: '/taller/bahia', texto: 'Bahía' }, { ruta: '/taller/vehiculos', texto: 'Expediente' }],
  ADMIN: [
    { ruta: '/admin/indicadores', texto: 'Indicadores' }, { ruta: '/admin/asignacion', texto: 'Asignación' },
    { ruta: '/admin/inventario', texto: 'Inventario' }, { ruta: '/admin/catalogo', texto: 'Catálogo' },
    { ruta: '/admin/usuarios', texto: 'Usuarios' }, { ruta: '/admin/bitacora', texto: 'Bitácora' },
    { ruta: '/recepcion/agenda', texto: 'Recepción' },
  ],
};

/** Barra superior: logo, menú del rol y "Salir". */
@Component({
  selector: 'app-barra-superior',
  imports: [RouterLink, RouterLinkActive, Icono],
  templateUrl: './barra-superior.html',
  styleUrl: './barra-superior.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BarraSuperior {
  protected readonly sesion = inject(SesionService);
  private readonly router = inject(Router);
  protected readonly abierto = signal(false);
  protected readonly iniciales = computed(() =>
    (this.sesion.usuario()?.full_name ?? '').split(' ').filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase());
  protected readonly menu = computed(() => {
    const rol = this.sesion.rol();
    return rol ? MENU[rol] : [];
  });

  protected salir(): void {
    const ir = () => void this.router.navigateByUrl('/ingresar');
    this.sesion.salir().subscribe({ next: ir, error: ir });
  }
}
