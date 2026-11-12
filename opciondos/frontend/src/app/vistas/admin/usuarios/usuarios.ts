import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { Campo } from '../../../componentes/campo/campo';
import { DialogoConfirmacion } from '../../../componentes/dialogo-confirmacion/dialogo-confirmacion';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { Columna, TablaDatos } from '../../../componentes/tabla-datos/tabla-datos';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { camposConError, mensajeError } from '../../../core/errores';
import { SesionService } from '../../../core/sesion.service';

interface UsuarioInterno {
  id: number;
  full_name: string;
  email: string;
  role: string;
  must_change_password: boolean;
  active?: boolean;
}

const ROLES: Record<string, string> = { RECEPTIONIST: 'Secretaria', MECHANIC: 'Mecánico', ADMIN: 'Administrador' };
const ERROR_SERVIDOR = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';

/** AD-05 Usuarios internos (HU-15): crear con contraseña temporal, cambiar rol y desactivar (RN-45). */
@Component({
  selector: 'app-vista-usuarios',
  imports: [FormsModule, Aviso, Boton, Campo, DialogoConfirmacion, InsigniaEstado, TablaDatos, Tarjeta],
  templateUrl: './usuarios.html',
  styleUrl: './usuarios.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaUsuarios {
  private readonly http = inject(HttpClient);
  protected readonly yo = inject(SesionService).usuario;
  protected readonly roles = Object.entries(ROLES);
  protected readonly nombreRol = ROLES;
  protected readonly columnas: Columna[] = [
    { clave: 'full_name', titulo: 'Nombre' }, { clave: 'email', titulo: 'Correo' }, { clave: 'role', titulo: 'Rol' },
    { clave: 'active', titulo: 'Estado' },
  ];

  protected readonly usuarios = signal<UsuarioInterno[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly exito = signal<string | null>(null);
  protected readonly invalidos = signal<string[]>([]);
  protected readonly creando = signal(false);
  protected readonly cambiando = signal<number | null>(null);
  protected readonly porDesactivar = signal<UsuarioInterno | null>(null);
  protected nuevo = { full_name: '', email: '', role: '', temporary_password: '' };

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    // shortcut: /usuarios aún no devuelve `active`; se completa con /usuarios/mecanicos (el único rol con inactivos en la semilla).
    forkJoin({
      todos: this.http.get<UsuarioInterno[]>('/api/usuarios'),
      mecanicos: this.http.get<{ id: number; active: boolean }[]>('/api/usuarios/mecanicos'),
    }).subscribe({
      next: ({ todos, mecanicos }) => {
        const activos = new Map(mecanicos.map((m) => [m.id, m.active]));
        this.usuarios.set(todos.filter((u) => u.role !== 'CUSTOMER')
          .map((u) => ({ ...u, active: u.active ?? activos.get(u.id) ?? true })));
      },
      error: (e: unknown) => this.error.set(mensajeError(e, ERROR_SERVIDOR)),
    });
  }

  protected crear(): void {
    this.error.set(null);
    this.exito.set(null);
    if (!this.nuevo.role) {
      this.invalidos.set(['role']);
      this.error.set('Seleccione el rol del usuario.');
      return;
    }
    this.creando.set(true);
    this.invalidos.set([]);
    this.http.post<UsuarioInterno>('/api/usuarios', this.nuevo).subscribe({
      next: (u) => {
        this.creando.set(false);
        this.usuarios.set([...this.usuarios(), { ...u, active: true }]);
        this.exito.set(`Usuario ${u.full_name} creado. Deberá cambiar la contraseña temporal en su primer ingreso.`);
        this.nuevo = { full_name: '', email: '', role: '', temporary_password: '' };
      },
      error: (e: unknown) => {
        this.creando.set(false);
        const campos = camposConError(e);
        const estado = e instanceof HttpErrorResponse ? e.status : 0;
        this.invalidos.set(campos.length ? campos : estado === 409 ? ['email'] : estado === 422 ? ['temporary_password'] : []);
        this.error.set(campos.length ? 'Por favor complete todos los campos obligatorios con un formato válido'
          : mensajeError(e, ERROR_SERVIDOR));
      },
    });
  }

  protected cambiarRol(u: UsuarioInterno, role: string): void {
    this.actualizar(u, { role }, `Rol de ${u.full_name} actualizado a ${ROLES[role]}.`);
  }

  protected cambiarEstado(u: UsuarioInterno, active: boolean): void {
    this.actualizar(u, { active }, active ? `${u.full_name} fue reactivado.`
      : `${u.full_name} fue desactivado y sus sesiones se cerraron.`);
  }

  protected invalido(campo: string): boolean {
    return this.invalidos().includes(campo);
  }

  protected fila(f: Record<string, unknown>): UsuarioInterno {
    return f as unknown as UsuarioInterno;
  }

  private actualizar(u: UsuarioInterno, cambio: Partial<UsuarioInterno>, mensaje: string): void {
    this.error.set(null);
    this.exito.set(null);
    this.cambiando.set(u.id);
    this.http.patch<UsuarioInterno>(`/api/usuarios/${u.id}`, cambio).subscribe({
      next: () => {
        this.cambiando.set(null);
        this.porDesactivar.set(null);
        this.usuarios.set(this.usuarios().map((x) => (x.id === u.id ? { ...x, ...cambio } : x)));
        this.exito.set(mensaje);
      },
      error: (e: unknown) => {
        this.cambiando.set(null);
        this.porDesactivar.set(null);
        this.error.set(mensajeError(e, ERROR_SERVIDOR));
      },
    });
  }
}
