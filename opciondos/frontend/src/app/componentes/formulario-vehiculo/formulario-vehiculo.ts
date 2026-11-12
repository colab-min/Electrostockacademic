import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Campo } from '../campo/campo';

/** Tipos de vehículo (HU-22) con su nombre en pantalla. */
export const TIPOS_VEHICULO: Record<string, string> = {
  E_BIKE: 'Bicicleta eléctrica', SCOOTER: 'Scooter', KICK_SCOOTER: 'Patineta', MOTORCYCLE: 'Moto',
  UNICYCLE: 'Monorueda', MICROCAR: 'Microcoche', QUADRICYCLE: 'Cuadriciclo',
};

export interface DatosVehiculo {
  type: string;
  serial_number: string;
  plate: string;
  brand: string;
  model: string;
  year: number | null;
  nominal_voltage_v: number | null;
  battery_capacity_ah: number | null;
  battery_cell: string;
  power_w: number | null;
  controller: string;
}

export const vehiculoVacio = (): DatosVehiculo => ({
  type: '', serial_number: '', plate: '', brand: '', model: '', year: null, nominal_voltage_v: null,
  battery_capacity_ah: null, battery_cell: '', power_w: null, controller: '',
});

const AYUDA_ERROR: Record<string, string> = {
  type: 'Elija el tipo de vehículo.',
  serial_number: 'Entre 5 y 30 letras, números o guiones.',
  plate: 'Formato ABC12D (moto) o ABC123.',
  brand: 'Campo obligatorio.', model: 'Campo obligatorio.', year: 'Año entre 1990 y 2100.',
  nominal_voltage_v: 'Número entero de voltios.', battery_capacity_ah: 'Número con máximo un decimal.',
  power_w: 'Número entero de vatios.',
};

/**
 * Formulario de vehículo compartido por SE-03 y CL-07 (HU-22). Va dentro del `<form>` de la vista,
 * que envía `datos`. `errores` trae, por campo, el texto a mostrar (formato o duplicado).
 */
@Component({
  selector: 'app-formulario-vehiculo',
  imports: [FormsModule, Campo],
  templateUrl: './formulario-vehiculo.html',
  styleUrl: './formulario-vehiculo.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FormularioVehiculo {
  readonly datos = input.required<DatosVehiculo>();
  readonly errores = input<Record<string, string>>({});
  protected readonly tipos = Object.entries(TIPOS_VEHICULO);

  protected error(campo: string): string | null {
    return this.errores()[campo] ?? null;
  }
}

/** Convierte la lista de campos inválidos del backend en textos por campo. */
export function erroresDeCampos(campos: string[], otros: Record<string, string> = {}): Record<string, string> {
  return Object.fromEntries(campos.map((c) => [c, otros[c] ?? AYUDA_ERROR[c] ?? 'Revise este campo.']));
}

/** Cuerpo para el backend: textos vacíos como null. */
export function cuerpoVehiculo(d: DatosVehiculo): Record<string, unknown> {
  return Object.fromEntries(Object.entries(d).map(([k, v]) => [k, v === '' ? null : v]));
}
