import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** Aviso (IS-4 7.7): error, información, advertencia o éxito. El tipo se lee por texto y borde. */
@Component({
  selector: 'app-aviso',
  templateUrl: './aviso.html',
  styleUrl: './aviso.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Aviso {
  readonly tipo = input<'error' | 'informacion' | 'advertencia' | 'exito'>('informacion');
  protected readonly rol = computed(() => (this.tipo() === 'error' ? 'alert' : 'status'));
}
