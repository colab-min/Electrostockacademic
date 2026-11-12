import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** Esqueleto de carga (IS-4 7.7) con la forma final: tarjeta o fila. Sin brillo con movimiento reducido. */
@Component({
  selector: 'app-esqueleto',
  templateUrl: './esqueleto.html',
  styleUrl: './esqueleto.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Esqueleto {
  readonly tipo = input<'tarjeta' | 'fila'>('tarjeta');
  readonly cantidad = input(3);
  protected readonly items = computed(() => Array.from({ length: this.cantidad() }, (_, i) => i));
}
