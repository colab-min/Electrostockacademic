import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { switchMap, timer } from 'rxjs';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { CabeceraVista } from '../../../componentes/cabecera-vista/cabecera-vista';
import { DialogoConfirmacion } from '../../../componentes/dialogo-confirmacion/dialogo-confirmacion';
import { Esqueleto } from '../../../componentes/esqueleto/esqueleto';
import { IlustracionVehiculo } from '../../../componentes/ilustracion-vehiculo/ilustracion-vehiculo';
import { ToastService } from '../../../componentes/toast/toast.service';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { mensajeError } from '../../../core/errores';
import { formatoFechaHora } from '../../../core/formato';

export interface OrdenTaller {
  id: number;
  number: string;
  status: string;
  priority: string | null;
  intake_reason: string;
  version: number;
  estimated_delivery_at: string | null;
  services: string[];
  vehicle: { type_label: string; brand: string; model: string; serial_number: string };
  transitions: { to_status: string; label: string }[];
}

const ERROR_INTERNO = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';

/** ME-01 Panel de bahía (HU-05): órdenes del mecánico, refrescadas cada 3 s. */
@Component({
  selector: 'app-vista-panel-bahia',
  imports: [RouterLink, Aviso, Boton, CabeceraVista, DialogoConfirmacion, Esqueleto, EstadoVacio, IlustracionVehiculo, InsigniaEstado],
  templateUrl: './panel-bahia.html',
  styleUrl: './panel-bahia.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaPanelBahia {
  private readonly http = inject(HttpClient);
  protected readonly ordenes = signal<OrdenTaller[] | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly procesando = signal<number | null>(null);
  protected readonly fecha = formatoFechaHora;
  private readonly toast = inject(ToastService);
  /** Segundo toque: la transición elegida espera confirmación en el diálogo. */
  protected readonly pendiente = signal<{ orden: OrdenTaller; to_status: string; label: string } | null>(null);

  protected confirmar(): void {
    const p = this.pendiente();
    if (p) this.avanzar(p.orden, p.to_status, p.label);
  }

  constructor() {
    timer(0, 3000)
      .pipe(switchMap(() => this.http.get<OrdenTaller[]>('/api/ordenes/mias')), takeUntilDestroyed())
      .subscribe({
        next: (o) => this.ordenes.set(o),
        error: (e: unknown) => this.error.set(mensajeError(e, ERROR_INTERNO)),
      });
  }

  protected avanzar(o: OrdenTaller, destino: string, label = ''): void {
    this.procesando.set(o.id);
    this.error.set(null);
    this.http.post(`/api/ordenes/${o.id}/estado`, { to_status: destino, version: o.version }).subscribe({
      next: () => {
        this.procesando.set(null);
        this.pendiente.set(null);
        this.toast.mostrar(`${o.number}: ${label || 'estado actualizado'}`);
        this.http.get<OrdenTaller[]>('/api/ordenes/mias').subscribe((l) => this.ordenes.set(l));
      },
      error: (e: unknown) => {
        this.procesando.set(null);
        this.pendiente.set(null);
        this.error.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }
}
