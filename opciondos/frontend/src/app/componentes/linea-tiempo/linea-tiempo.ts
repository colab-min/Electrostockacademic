import { ChangeDetectionStrategy, Component, effect, input, signal } from '@angular/core';

export interface EventoLinea {
  titulo: string;
  fecha: string;
  detalle?: string | null;
  /** Por defecto: todos completos y el último es el actual. `pendiente` se dibuja punteado. */
  estado?: 'completo' | 'actual' | 'pendiente';
}

/** Línea de tiempo con hitos completos, actual y pendientes; el hito nuevo se ilumina un instante. */
@Component({
  selector: 'app-linea-tiempo',
  templateUrl: './linea-tiempo.html',
  styleUrl: './linea-tiempo.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LineaTiempo {
  readonly eventos = input<EventoLinea[]>([]);
  protected readonly nuevo = signal(-1);
  private previos = -1;

  constructor() {
    effect((onCleanup) => {
      const n = this.eventos().length;
      if (this.previos >= 0 && n > this.previos) {
        this.nuevo.set(n - 1);
        const t = setTimeout(() => this.nuevo.set(-1), 1600);
        onCleanup(() => clearTimeout(t));
      }
      this.previos = n;
    });
  }

  protected estado(e: EventoLinea, i: number): string {
    return e.estado ?? (i === this.eventos().length - 1 ? 'actual' : 'completo');
  }

  protected formato(iso: string): string {
    return new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso));
  }
}
