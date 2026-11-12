import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Icono } from '../icono/icono';

/**
 * Etiqueta siempre visible + control proyectado + ayuda + error con icono y texto.
 * El control debe tener el mismo `id` que `para` y `[attr.aria-invalid]` cuando hay error.
 */
@Component({
  selector: 'app-campo',
  imports: [Icono],
  templateUrl: './campo.html',
  styleUrl: './campo.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Campo {
  readonly etiqueta = input.required<string>();
  readonly para = input.required<string>();
  readonly ayuda = input<string | null>(null);
  readonly error = input<string | null>(null);
}
