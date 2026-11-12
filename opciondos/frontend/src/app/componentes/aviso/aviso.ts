import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Icono } from '../icono/icono';
import { NombreIcono } from '../icono/iconos';

type Tipo = 'error' | 'informacion' | 'advertencia' | 'exito' | 'demostracion';
const ICONO: Record<Tipo, NombreIcono> = {
  error: 'error', informacion: 'info', advertencia: 'alerta', exito: 'check-circulo', demostracion: 'info',
};

/** Aviso (IS-4 7.7): el tipo se lee por icono, texto y borde, no solo por color. */
@Component({
  selector: 'app-aviso',
  imports: [Icono],
  templateUrl: './aviso.html',
  styleUrl: './aviso.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Aviso {
  readonly tipo = input<Tipo>('informacion');
  protected readonly rol = computed(() => (this.tipo() === 'error' ? 'alert' : 'status'));
  protected readonly icono = computed(() => ICONO[this.tipo()]);
}
