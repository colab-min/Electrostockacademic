import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export interface EventoLinea {
  titulo: string;
  fecha: string;
  detalle?: string | null;
}

/** Línea de tiempo con fecha y hora (PU-03, ME-02, ME-03, AD-06). */
@Component({
  selector: 'app-linea-tiempo',
  templateUrl: './linea-tiempo.html',
  styleUrl: './linea-tiempo.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LineaTiempo {
  readonly eventos = input<EventoLinea[]>([]);
  protected formato(iso: string): string {
    return new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
  }
}
