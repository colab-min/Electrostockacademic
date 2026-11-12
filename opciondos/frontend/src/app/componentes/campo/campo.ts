import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Etiqueta + control + ayuda + error. El control (input, select, textarea) va proyectado y debe tener
 * el mismo `id` que `para`, y `[attr.aria-invalid]` cuando hay error.
 */
@Component({
  selector: 'app-campo',
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
