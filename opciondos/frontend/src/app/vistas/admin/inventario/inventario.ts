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
import { camposConError, mensajeError } from '../../../core/errores';
import { formatoFechaHora, formatoPesos } from '../../../core/formato';

export interface Repuesto {
  id: number;
  sku: string;
  name: string;
  category: string;
  purchase_price: number;
  sale_price: number;
  physical_stock: number;
  reserved_stock: number;
  available: number;
  min_threshold: number;
  compatible_voltage_v: number | null;
  active: boolean;
  alerta: boolean;
}

interface Movimiento {
  id: number;
  sku: string;
  name: string;
  type: string;
  quantity: number;
  reason: string | null;
  created_at: string;
}

export const CATEGORIAS: Record<string, string> = {
  BATTERY: 'Batería', CONTROLLER: 'Controlador', MOTOR: 'Motor', CHARGER: 'Cargador', BRAKES: 'Frenos',
  WHEELS: 'Ruedas', CONTROLS: 'Mandos', OTHER: 'Otro',
};
const TIPOS: Record<string, string> = { IN: 'Entrada', WRITE_OFF: 'Baja', ADJUSTMENT: 'Ajuste', CONSUMPTION: 'Consumo' };
const ERROR_INTERNO = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';

/** AD-03 Inventario (HU-08 alertas, HU-27 movimientos, HU-29 alta y edición). */
@Component({
  selector: 'app-vista-inventario',
  imports: [FormsModule, Aviso, Boton, Campo, EstadoVacio, InsigniaEstado, TablaDatos, Tarjeta],
  templateUrl: './inventario.html',
  styleUrl: './inventario.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaInventario {
  private readonly http = inject(HttpClient);
  protected readonly categorias = Object.entries(CATEGORIAS);
  protected readonly tipos = TIPOS;
  protected readonly pesos = formatoPesos;
  protected readonly fechaHora = formatoFechaHora;
  protected readonly repuestos = signal<Repuesto[] | null>(null);
  protected readonly movimientos = signal<Movimiento[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly exito = signal<string | null>(null);
  protected readonly categoria = signal('');
  protected readonly soloAlertas = signal(false);

  protected readonly columnas: Columna[] = [
    { clave: 'sku', titulo: 'SKU' }, { clave: 'name', titulo: 'Nombre' }, { clave: 'category', titulo: 'Categoría' },
    { clave: 'physical_stock', titulo: 'Físico' }, { clave: 'reserved_stock', titulo: 'Reservado' },
    { clave: 'available', titulo: 'Disponible' }, { clave: 'min_threshold', titulo: 'Umbral' }, { clave: 'estado', titulo: 'Estado' },
  ];
  protected readonly filas = computed(() => (this.repuestos() ?? []).filter((r) =>
    (!this.categoria() || r.category === this.categoria()) && (!this.soloAlertas() || r.alerta)) as unknown as Record<string, unknown>[]);

  // Formulario de alta o edición (HU-29)
  protected readonly editando = signal<Repuesto | 'nuevo' | null>(null);
  protected form = this.vacio();
  protected readonly errorForm = signal<string | null>(null);
  protected readonly camposError = signal<string[]>([]);
  protected readonly guardando = signal(false);

  // Movimiento (HU-27)
  protected mov = { part_id: null as number | null, type: 'IN', quantity: 1, reason: '' };
  protected readonly errorMov = signal<string | null>(null);
  protected readonly moviendo = signal(false);

  constructor() {
    this.cargar();
  }

  protected cargar(): void {
    this.error.set(null);
    this.http.get<Repuesto[]>('/api/inventario/repuestos').subscribe({
      next: (r) => this.repuestos.set(r),
      error: (e: unknown) => this.error.set(mensajeError(e, ERROR_INTERNO)),
    });
    this.http.get<Movimiento[]>('/api/inventario/movimientos').subscribe({ next: (m) => this.movimientos.set(m) });
  }

  protected nombreCategoria(c: string): string {
    return CATEGORIAS[c] ?? c;
  }

  protected comoRepuesto(fila: Record<string, unknown>): Repuesto {
    return fila as unknown as Repuesto;
  }

  private vacio() {
    return { sku: '', name: '', category: 'BATTERY', purchase_price: 0, sale_price: 0, physical_stock: 0, min_threshold: 0,
      compatible_voltage_v: null as number | null, active: true };
  }

  protected nuevo(): void {
    this.form = this.vacio();
    this.errorForm.set(null);
    this.camposError.set([]);
    this.editando.set('nuevo');
  }

  protected editar(r: Repuesto): void {
    this.form = { ...r };
    this.errorForm.set(null);
    this.camposError.set([]);
    this.editando.set(r);
  }

  protected guardar(): void {
    const actual = this.editando();
    if (!actual) return;
    const f = this.form;
    const voltaje = f.compatible_voltage_v || null;
    const peticion = actual === 'nuevo'
      ? this.http.post<Repuesto>('/api/inventario/repuestos', { ...f, compatible_voltage_v: voltaje })
      : this.http.patch<Repuesto>(`/api/inventario/repuestos/${actual.id}`, {
        name: f.name, category: f.category, purchase_price: f.purchase_price, sale_price: f.sale_price,
        min_threshold: f.min_threshold, compatible_voltage_v: voltaje, active: f.active,
      });
    this.guardando.set(true);
    this.errorForm.set(null);
    peticion.subscribe({
      next: (r) => {
        this.guardando.set(false);
        this.editando.set(null);
        this.exito.set(`Repuesto ${r.sku} guardado.`);
        this.cargar();
      },
      error: (e: unknown) => {
        this.guardando.set(false);
        this.camposError.set(camposConError(e));
        this.errorForm.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }

  protected registrarMovimiento(): void {
    this.moviendo.set(true);
    this.errorMov.set(null);
    this.http.post<Repuesto>('/api/inventario/movimientos', { ...this.mov, reason: this.mov.reason || null }).subscribe({
      next: (r) => {
        this.moviendo.set(false);
        this.exito.set(`Movimiento registrado: ${r.name} queda con ${r.physical_stock} en físico y ${r.available} disponibles.`);
        this.mov = { part_id: null, type: 'IN', quantity: 1, reason: '' };
        this.cargar();
      },
      error: (e: unknown) => {
        this.moviendo.set(false);
        this.errorMov.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }
}
