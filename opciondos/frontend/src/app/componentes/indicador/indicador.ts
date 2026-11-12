import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Icono } from '../icono/icono';
import { NombreIcono } from '../icono/iconos';

/** Indicador (KPI): número grande y variación con flecha y texto, no solo color. */
@Component({
  selector: 'app-indicador',
  imports: [Icono],
  templateUrl: './indicador.html',
  styleUrl: './indicador.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Indicador {
  readonly titulo = input.required<string>();
  readonly valor = input.required<string | number>();
  readonly detalle = input<string | null>(null);
  /** Variación en porcentaje frente al periodo anterior (positiva o negativa). */
  readonly variacion = input<number | null>(null);
  readonly icono = input<NombreIcono>('grafico');
  protected readonly sube = computed(() => (this.variacion() ?? 0) >= 0);
}
