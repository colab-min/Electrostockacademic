import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { DialogoConfirmacion } from '../../../componentes/dialogo-confirmacion/dialogo-confirmacion';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoFechaHora } from '../../../core/formato';
import { Cita, FUERA_VENTANA, textoLimite } from '../agendar/cita';

interface Vehiculo {
  id: number;
  type: string;
  serial_number: string;
  plate: string | null;
  brand: string;
  model: string;
  nominal_voltage_v: number;
}

/** CL-01 Mis citas y vehículos (HU-11, HU-22, HU-30). */
@Component({
  selector: 'app-vista-mis-citas',
  imports: [RouterLink, Aviso, Boton, DialogoConfirmacion, EstadoVacio, InsigniaEstado, Tarjeta],
  templateUrl: './mis-citas.html',
  styleUrl: './mis-citas.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaMisCitas {
  private readonly http = inject(HttpClient);
  protected readonly citas = signal<Cita[] | null>(null);
  protected readonly vehiculos = signal<Vehiculo[] | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly exito = signal<string | null>(null);
  protected readonly aCancelar = signal<Cita | null>(null);
  protected readonly errorCancelar = signal<string | null>(null);
  protected readonly procesando = signal(false);
  protected readonly fechaHora = formatoFechaHora;
  protected readonly limite = textoLimite;
  protected readonly fueraVentana = FUERA_VENTANA;

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.error.set(null);
    this.http.get<Cita[]>('/api/agenda/citas/mias').subscribe({
      next: (c) => this.citas.set(c),
      error: (e: unknown) => this.error.set(mensajeError(e)),
    });
    this.http.get<Vehiculo[]>('/api/clientes/mis-vehiculos').subscribe({
      next: (v) => this.vehiculos.set(v),
      error: (e: unknown) => this.error.set(mensajeError(e)),
    });
  }

  protected abrirCancelar(c: Cita): void {
    this.errorCancelar.set(null);
    this.aCancelar.set(c);
  }

  protected cancelar(): void {
    const c = this.aCancelar();
    if (!c) return;
    this.procesando.set(true);
    this.http.post<Cita>(`/api/agenda/citas/${c.id}/cancelar`, null).subscribe({
      next: () => {
        this.procesando.set(false);
        this.aCancelar.set(null);
        this.exito.set(`Cancelaste la cita ${c.code}. El cupo y los repuestos quedaron libres.`);
        this.cargar();
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        this.errorCancelar.set(mensajeError(e));
      },
    });
  }
}
