import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type TipoVehiculo =
  | 'E_BIKE' | 'SCOOTER' | 'KICK_SCOOTER' | 'MOTORCYCLE' | 'UNICYCLE' | 'MICROCAR' | 'QUADRICYCLE';

const NOMBRES: Record<TipoVehiculo, string> = {
  E_BIKE: 'Bicicleta eléctrica', SCOOTER: 'Scooter', KICK_SCOOTER: 'Patineta', MOTORCYCLE: 'Moto eléctrica',
  UNICYCLE: 'Monorueda', MICROCAR: 'Microcoche', QUADRICYCLE: 'Cuadriciclo',
};

/** Ilustración de vehículo (IS-4 7.5): los 7 SVG exportados de makups3 (Componentes, "Ilustración de vehículo"). */
@Component({
  selector: 'app-ilustracion-vehiculo',
  templateUrl: './ilustracion-vehiculo.html',
  styleUrl: './ilustracion-vehiculo.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class IlustracionVehiculo {
  /** Código del tipo; también acepta el nombre en español que devuelve el seguimiento público. */
  readonly tipo = input.required<string>();
  readonly tamano = input<'pequena' | 'mediana' | 'grande'>('mediana');
  protected readonly codigo = computed<TipoVehiculo>(() => {
    const t = this.tipo();
    if (t in NOMBRES) return t as TipoVehiculo;
    const texto = t.toLowerCase();
    if (texto.includes('bici')) return 'E_BIKE';
    if (texto.includes('patineta')) return 'KICK_SCOOTER';
    if (texto.includes('moto')) return 'MOTORCYCLE';
    if (texto.includes('monorueda')) return 'UNICYCLE';
    if (texto.includes('microcoche')) return 'MICROCAR';
    if (texto.includes('cuadriciclo')) return 'QUADRICYCLE';
    return 'SCOOTER';
  });
  protected readonly nombre = computed(() => NOMBRES[this.codigo()]);
}
