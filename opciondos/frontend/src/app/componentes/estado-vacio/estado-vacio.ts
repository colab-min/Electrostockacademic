import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Estado vacío (IS-4 7.7): motivo y, si el rol puede resolverlo, la acción proyectada. */
@Component({
  selector: 'app-estado-vacio',
  templateUrl: './estado-vacio.html',
  styleUrl: './estado-vacio.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EstadoVacio {
  readonly titulo = input.required<string>();
  readonly mensaje = input<string | null>(null);
}
