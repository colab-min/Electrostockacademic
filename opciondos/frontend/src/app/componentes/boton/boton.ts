import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Icono } from '../icono/icono';
import { NombreIcono } from '../icono/iconos';

/** Botón (IS-4 7.6). Primario con sombra riso caqui que se "estampa" al presionar. */
@Component({
  selector: 'app-boton',
  imports: [Icono],
  templateUrl: './boton.html',
  styleUrl: './boton.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Boton {
  readonly variante = input<'primario' | 'secundario' | 'peligro' | 'neutro'>('primario');
  readonly tipo = input<'button' | 'submit'>('button');
  readonly tamano = input<'normal' | 'grande'>('normal');
  readonly icono = input<NombreIcono | null>(null);
  readonly deshabilitado = input(false);
  readonly procesando = input(false);
}
