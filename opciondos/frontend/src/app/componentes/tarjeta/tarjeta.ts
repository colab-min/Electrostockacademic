import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Tarjeta con elevación nivel 1; `destacada` agrega el borde gardenia; `interactiva` responde al hover. */
@Component({
  selector: 'app-tarjeta',
  templateUrl: './tarjeta.html',
  styleUrl: './tarjeta.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Tarjeta {
  readonly titulo = input<string | null>(null);
  readonly destacada = input(false);
  readonly interactiva = input(false);
}
