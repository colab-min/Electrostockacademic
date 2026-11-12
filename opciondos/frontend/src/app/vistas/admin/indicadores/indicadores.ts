import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { Campo } from '../../../componentes/campo/campo';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { Columna, TablaDatos } from '../../../componentes/tabla-datos/tabla-datos';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoPesos } from '../../../core/formato';

interface Resumen {
  ingresos: number;
  ordenes_por_estado: { estado: string; cantidad: number }[];
  ocupacion: { reservadas: number; capacidad: number; porcentaje: number };
  repuestos: { sku: string; name: string; cantidad: number }[];
  satisfaccion: { promedio: number | null; respuestas: number };
}

const iso = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

/** AD-01 Indicadores y reportes (HU-14): cifras del rango elegido, sin librerías de gráficos. */
@Component({
  selector: 'app-vista-indicadores',
  imports: [FormsModule, Aviso, Boton, Campo, EstadoVacio, InsigniaEstado, TablaDatos, Tarjeta],
  templateUrl: './indicadores.html',
  styleUrl: './indicadores.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaIndicadores {
  private readonly http = inject(HttpClient);
  protected readonly pesos = formatoPesos;
  protected desde = iso(new Date(Date.now() - 30 * 86_400_000));
  protected hasta = iso(new Date());

  protected readonly resumen = signal<Resumen | null>(null);
  protected readonly procesando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly totalOrdenes = computed(() =>
    (this.resumen()?.ordenes_por_estado ?? []).reduce((suma, e) => suma + e.cantidad, 0));
  protected readonly columnasEstado: Columna[] = [{ clave: 'estado', titulo: 'Estado' }, { clave: 'cantidad', titulo: 'Órdenes' }];
  protected readonly columnasRepuestos: Columna[] = [
    { clave: 'sku', titulo: 'SKU' }, { clave: 'name', titulo: 'Repuesto' }, { clave: 'cantidad', titulo: 'Unidades' },
  ];

  constructor() {
    this.generar();
  }

  protected generar(): void {
    this.procesando.set(true);
    this.error.set(null);
    this.http.get<Resumen>('/api/reportes/resumen', { params: { desde: this.desde, hasta: this.hasta } }).subscribe({
      next: (r) => {
        this.procesando.set(false);
        this.resumen.set(r);
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        this.error.set(mensajeError(e, 'No fue posible completar la acción. Intente de nuevo en unos segundos.'));
      },
    });
  }
}
