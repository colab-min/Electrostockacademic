import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Icono } from '../icono/icono';
import { NombreIcono } from '../icono/iconos';

/** Estado vacío (IS-4 7.7): motivo y, si el rol puede resolverlo, la acción proyectada. */
@Component({
  selector: 'app-estado-vacio',
  imports: [Icono],
  templateUrl: './estado-vacio.html',
  styleUrl: './estado-vacio.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EstadoVacio {
  readonly titulo = input.required<string>();
  readonly mensaje = input<string | null>(null);
  readonly icono = input<NombreIcono>('bandeja');
}
