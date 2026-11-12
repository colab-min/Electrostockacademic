import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, TemplateRef, input } from '@angular/core';

export interface Columna {
  clave: string;
  titulo: string;
}

/**
 * Tabla responsive (en celular cada fila se vuelve tarjeta). Para celdas a medida pasa `celda`
 * (contexto: fila y columna) y para acciones por fila, `acciones` (contexto: fila).
 */
@Component({
  selector: 'app-tabla-datos',
  imports: [NgTemplateOutlet],
  templateUrl: './tabla-datos.html',
  styleUrl: './tabla-datos.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TablaDatos {
  readonly columnas = input.required<Columna[]>();
  readonly filas = input<Record<string, unknown>[]>([]);
  readonly titulo = input.required<string>();
  readonly celda = input<TemplateRef<{ $implicit: Record<string, unknown>; columna: Columna }> | null>(null);
  readonly acciones = input<TemplateRef<{ $implicit: Record<string, unknown> }> | null>(null);
}
