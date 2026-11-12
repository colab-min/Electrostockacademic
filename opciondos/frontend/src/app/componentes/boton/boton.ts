import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Botón con cuatro variantes (IS-4 7.6). Con `procesando` muestra "Procesando…" y se deshabilita. */
@Component({
  selector: 'app-boton',
  templateUrl: './boton.html',
  styleUrl: './boton.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Boton {
  readonly variante = input<'primario' | 'secundario' | 'peligro' | 'neutro'>('primario');
  readonly tipo = input<'button' | 'submit'>('button');
  readonly deshabilitado = input(false);
  readonly procesando = input(false);
}
