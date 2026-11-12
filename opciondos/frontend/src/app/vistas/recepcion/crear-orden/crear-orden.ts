import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { BuscadorVehiculo } from '../../../componentes/buscador-vehiculo/buscador-vehiculo';
import { Campo } from '../../../componentes/campo/campo';
import { DialogoConfirmacion } from '../../../componentes/dialogo-confirmacion/dialogo-confirmacion';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { DatosTicket, TicketOrden } from '../../../componentes/ticket-orden/ticket-orden';
import { mensajeError } from '../../../core/errores';
import { formatoFechaHora } from '../../../core/formato';

interface Cita {
  id: number;
  code: string;
  starts_at: string;
  service: { name: string };
  customer: { full_name: string };
  vehicle: { type_label: string; brand: string; model: string; serial_number: string; plate: string | null };
}
export interface OrdenResumen {
  id: number;
  number: string;
  status: string;
  priority: string | null;
  version: number;
  intake_reason: string;
  created_at: string;
  queue_position: number | null;
  vehicle: { type_label: string; brand: string; model: string; serial_number: string };
}
interface Creada extends OrdenResumen { tracking_code: string }

const ERROR_INTERNO = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';
const CANCELABLES = ['RECEIVED', 'ASSIGNED', 'PENDING_INSTALLATION'];

/** SE-04 Crear y cancelar orden (HU-23, HU-17). El código de seguimiento se muestra una sola vez. */
@Component({
  selector: 'app-vista-crear-orden',
  imports: [FormsModule, Aviso, Boton, BuscadorVehiculo, Campo, DialogoConfirmacion, EstadoVacio, InsigniaEstado,
    Tarjeta, TicketOrden],
  templateUrl: './crear-orden.html',
  styleUrl: './crear-orden.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaCrearOrden implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly citas = signal<Cita[] | null>(null);
  protected readonly ordenes = signal<OrdenResumen[]>([]);
  protected readonly creada = signal<Creada | null>(null);
  protected readonly ticket = signal<DatosTicket | null>(null);
  protected readonly copiado = signal(false);
  protected readonly buscando = signal(false);
  protected readonly procesando = signal<number | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly aCancelar = signal<OrdenResumen | null>(null);
  protected readonly errorCancelar = signal<string | null>(null);
  protected readonly cancelando = signal(false);
  protected readonly fecha = formatoFechaHora;
  protected motivos: Record<number, string> = {};
  protected motivoCancelar = '';

  ngOnInit(): void {
    this.buscar('');
    this.cargarOrdenes();
  }

  protected buscar(q: string): void {
    this.buscando.set(true);
    this.error.set(null);
    this.http.get<Cita[]>('/api/ordenes/citas-del-dia', { params: { q } }).subscribe({
      next: (c) => {
        this.buscando.set(false);
        this.citas.set(c);
      },
      error: (e: unknown) => {
        this.buscando.set(false);
        this.error.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }

  private cargarOrdenes(): void {
    this.http.get<OrdenResumen[]>('/api/ordenes').subscribe({
      next: (o) => this.ordenes.set(o.filter((x) => CANCELABLES.includes(x.status))),
      error: (e: unknown) => this.error.set(mensajeError(e, ERROR_INTERNO)),
    });
  }

  protected crear(c: Cita): void {
    this.procesando.set(c.id);
    this.error.set(null);
    this.http.post<Creada>('/api/ordenes', { appointment_id: c.id, intake_reason: this.motivos[c.id] || null }).subscribe({
      next: (o) => {
        this.procesando.set(null);
        this.creada.set(o);
        this.copiado.set(false);
        this.http.get<DatosTicket>(`/api/facturacion/ordenes/${o.id}/ticket`, { params: { codigo: o.tracking_code } })
          .subscribe({ next: (t) => this.ticket.set(t), error: () => this.ticket.set(null) });
        this.buscar('');
        this.cargarOrdenes();
      },
      error: (e: unknown) => {
        this.procesando.set(null);
        this.error.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }

  protected copiar(codigo: string): void {
    void navigator.clipboard?.writeText(codigo).then(() => this.copiado.set(true));
  }

  protected pedirCancelar(o: OrdenResumen): void {
    this.motivoCancelar = '';
    this.errorCancelar.set(null);
    this.aCancelar.set(o);
  }

  protected cancelar(): void {
    const o = this.aCancelar();
    if (!o) return;
    this.cancelando.set(true);
    this.http.post(`/api/ordenes/${o.id}/cancelar`, { version: o.version, reason: this.motivoCancelar.trim() || null })
      .subscribe({
        next: () => {
          this.cancelando.set(false);
          this.aCancelar.set(null);
          this.cargarOrdenes();
        },
        error: (e: unknown) => {
          this.cancelando.set(false);
          this.errorCancelar.set(mensajeError(e, ERROR_INTERNO));
        },
      });
  }
}
