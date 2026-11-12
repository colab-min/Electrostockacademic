import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { Campo } from '../../../componentes/campo/campo';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { Columna, TablaDatos } from '../../../componentes/tabla-datos/tabla-datos';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoFechaHora } from '../../../core/formato';

interface Registro {
  id: number;
  entity: string;
  entity_id: number | null;
  action: string;
  user_name: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

/** AD-06 Bitácora de auditoría (HU-20): solo lectura, filtros por entidad y acción. */
@Component({
  selector: 'app-vista-bitacora',
  imports: [FormsModule, Aviso, Boton, Campo, EstadoVacio, TablaDatos, Tarjeta],
  templateUrl: './bitacora.html',
  styleUrl: './bitacora.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaBitacora {
  private readonly http = inject(HttpClient);
  protected readonly fecha = formatoFechaHora;
  protected readonly columnas: Columna[] = [
    { clave: 'created_at', titulo: 'Fecha y hora' }, { clave: 'entity', titulo: 'Entidad' }, { clave: 'action', titulo: 'Acción' },
    { clave: 'user_name', titulo: 'Usuario' }, { clave: 'detail', titulo: 'Detalle' },
  ];
  protected readonly registros = signal<Registro[] | null>(null);
  protected readonly opciones = signal<{ entidades: string[]; acciones: string[] }>({ entidades: [], acciones: [] });
  protected readonly procesando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected filtro = { entidad: '', accion: '' };

  constructor() {
    this.http.get<{ entidades: string[]; acciones: string[] }>('/api/auditoria/opciones').subscribe({
      next: (o) => this.opciones.set(o),
      error: () => undefined,
    });
    this.filtrar();
  }

  protected filtrar(): void {
    this.procesando.set(true);
    this.error.set(null);
    const params = Object.fromEntries(Object.entries(this.filtro).filter(([, v]) => v));
    this.http.get<Registro[]>('/api/auditoria/bitacora', { params }).subscribe({
      next: (r) => {
        this.procesando.set(false);
        this.registros.set(r);
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        this.error.set(mensajeError(e, 'No fue posible completar la acción. Intente de nuevo en unos segundos.'));
      },
    });
  }

  protected detalle(d: unknown): string {
    return d ? JSON.stringify(d) : '';
  }
}
