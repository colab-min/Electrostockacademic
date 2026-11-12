import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';

export interface DatoBarra {
  etiqueta: string;
  valor: number;
}

/**
 * Gráfico de barras horizontales en SVG (sin librería). Cada barra lleva su valor escrito,
 * tooltip al pasar o enfocar, y una tabla oculta para lectores de pantalla.
 */
@Component({
  selector: 'app-grafico-barras',
  templateUrl: './grafico-barras.html',
  styleUrl: './grafico-barras.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class GraficoBarras {
  readonly titulo = input.required<string>();
  readonly datos = input<DatoBarra[]>([]);
  readonly unidad = input('');
  readonly leyenda = input<string | null>(null);
  protected readonly activo = signal<number | null>(null);
  protected readonly maximo = computed(() => Math.max(1, ...this.datos().map((d) => d.valor)));

  protected ancho(valor: number): number {
    return Math.max(2, (valor / this.maximo()) * 100);
  }

  protected texto(valor: number): string {
    return `${new Intl.NumberFormat('es-CO').format(valor)}${this.unidad() ? ' ' + this.unidad() : ''}`;
  }
}
