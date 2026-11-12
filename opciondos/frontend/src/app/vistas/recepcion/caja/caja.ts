import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { Campo } from '../../../componentes/campo/campo';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { DatosTicket, TicketOrden } from '../../../componentes/ticket-orden/ticket-orden';
import { mensajeError } from '../../../core/errores';
import { formatoPesos } from '../../../core/formato';

interface OrdenCaja {
  id: number;
  number: string;
  status: string;
  intake_reason: string;
  vehicle: { type_label: string; brand: string; model: string; serial_number: string };
  services: string[];
  labor: number;
  parts: number;
  subtotal: number;
  vat: number;
  total: number;
  receipt_number: string | null;
  survey_url: string | null;
}

const ERROR_INTERNO = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';

/** SE-05 Liquidar, cobrar y entregar (HU-13) y reimpresión del ticket sin código (HU-17). */
@Component({
  selector: 'app-vista-caja',
  imports: [FormsModule, RouterLink, Aviso, Boton, Campo, EstadoVacio, InsigniaEstado, Tarjeta, TicketOrden],
  templateUrl: './caja.html',
  styleUrl: './caja.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaCaja implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly ordenes = signal<OrdenCaja[] | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly errores = signal<Record<number, string>>({});
  protected readonly procesando = signal<number | null>(null);
  protected readonly entregada = signal<OrdenCaja | null>(null);
  protected readonly ticket = signal<DatosTicket | null>(null);
  protected readonly pesos = formatoPesos;
  protected montos: Record<number, number | null> = {};
  protected metodos: Record<number, string> = {};

  ngOnInit(): void {
    this.cargar();
  }

  private cargar(): void {
    this.http.get<OrdenCaja[]>('/api/facturacion/ordenes').subscribe({
      next: (o) => this.ordenes.set(o),
      error: (e: unknown) => this.error.set(mensajeError(e, ERROR_INTERNO)),
    });
  }

  private ejecutar(o: OrdenCaja, paso: 'liquidar' | 'pagos' | 'entregar', cuerpo: object = {}): void {
    this.procesando.set(o.id);
    this.errores.update((e) => ({ ...e, [o.id]: '' }));
    this.http.post<OrdenCaja>(`/api/facturacion/ordenes/${o.id}/${paso}`, cuerpo).subscribe({
      next: (r) => {
        this.procesando.set(null);
        if (paso === 'entregar') this.entregada.set(r);
        this.cargar();
      },
      error: (e: unknown) => {
        this.procesando.set(null);
        this.errores.update((x) => ({ ...x, [o.id]: mensajeError(e, ERROR_INTERNO) }));
      },
    });
  }

  protected liquidar(o: OrdenCaja): void {
    this.ejecutar(o, 'liquidar');
  }

  protected pagar(o: OrdenCaja): void {
    this.ejecutar(o, 'pagos', { amount: Number(this.montos[o.id] ?? 0), method: this.metodos[o.id] ?? 'CASH' });
  }

  protected entregar(o: OrdenCaja): void {
    this.ejecutar(o, 'entregar');
  }

  protected verTicket(o: OrdenCaja): void {
    this.http.get<DatosTicket>(`/api/facturacion/ordenes/${o.id}/ticket`).subscribe({
      next: (t) => this.ticket.set(t),
      error: (e: unknown) => this.error.set(mensajeError(e, ERROR_INTERNO)),
    });
  }
}
