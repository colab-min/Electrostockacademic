import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

export type EstadoFranja = 'libre' | 'sin-cupo' | 'bloqueado';

/** Franja de 1 hora con su estado. "Sin cupo" y "Bloqueado" se muestran como texto (IS-4 8). */
@Component({
  selector: 'app-franja-horaria',
  templateUrl: './franja-horaria.html',
  styleUrl: './franja-horaria.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FranjaHoraria {
  readonly hora = input.required<string>();
  readonly estado = input<EstadoFranja>('libre');
  readonly seleccionada = input(false);
  /** Texto adicional (p. ej. "2 de 3 cupos" o el repuesto que se apartará). */
  readonly detalle = input<string | null>(null);
  readonly elegir = output<void>();
  protected readonly etiqueta = computed(() =>
    ({ libre: 'Disponible', 'sin-cupo': 'Sin cupo', bloqueado: 'Bloqueado' })[this.estado()]);
}
