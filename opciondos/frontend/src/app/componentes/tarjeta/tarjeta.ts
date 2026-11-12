import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-tarjeta',
  templateUrl: './tarjeta.html',
  styleUrl: './tarjeta.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Tarjeta {
  readonly titulo = input<string | null>(null);
  readonly destacada = input(false);
}
