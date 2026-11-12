import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { IlustracionVehiculo } from '../ilustracion-vehiculo/ilustracion-vehiculo';

/** Cabecera de vista: título grande, insignia de las HU, línea de contexto e ilustración opcional. */
@Component({
  selector: 'app-cabecera-vista',
  imports: [IlustracionVehiculo],
  templateUrl: './cabecera-vista.html',
  styleUrl: './cabecera-vista.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CabeceraVista {
  readonly titulo = input.required<string>();
  readonly hu = input<string | null>(null);
  readonly contexto = input<string | null>(null);
  readonly vehiculo = input<string | null>(null);
}
