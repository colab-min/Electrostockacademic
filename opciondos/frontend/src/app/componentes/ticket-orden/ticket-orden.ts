import { ChangeDetectionStrategy, Component, ViewEncapsulation, input } from '@angular/core';
import { formatoFechaHora } from '../../core/formato';

export interface DatosTicket {
  taller: string;
  number: string;
  tracking_code: string | null;
  fecha_ingreso: string;
  tipo: string;
  marca: string;
  modelo: string;
  serie_ultimos4: string;
  motivo: string;
}

/**
 * Ticket de 80 mm de la orden (HU-17, SE-04 y SE-05). "Imprimir ticket" usa la impresión del navegador,
 * que también permite guardar en PDF. Sin QR: no hay librería de QR en el proyecto.
 */
@Component({
  selector: 'app-ticket-orden',
  templateUrl: './ticket-orden.html',
  styleUrl: './ticket-orden.css',
  encapsulation: ViewEncapsulation.None, // la hoja de impresión debe ocultar el resto de la página
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TicketOrden {
  readonly datos = input.required<DatosTicket>();
  protected readonly fecha = formatoFechaHora;

  protected imprimir(): void {
    window.print();
  }
}
