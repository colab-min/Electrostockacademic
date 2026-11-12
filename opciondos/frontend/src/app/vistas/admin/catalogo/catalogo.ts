import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { Campo } from '../../../componentes/campo/campo';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { camposConError, mensajeError } from '../../../core/errores';
import { formatoPesos } from '../../../core/formato';
import { Repuesto } from '../inventario/inventario';

interface LineaRepuesto {
  part_id: number;
  sku: string;
  name: string;
  quantity: number;
  available: number;
}

interface Servicio {
  id: number;
  code: string;
  name: string;
  labor_price: number;
  duration_min: number;
  active: boolean;
  repuestos: LineaRepuesto[];
  advertencia?: string | null;
}

const ERROR_INTERNO = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';

/** AD-04 Catálogo de servicios (HU-18) y repuestos por servicio (HU-26). */
@Component({
  selector: 'app-vista-catalogo',
  imports: [FormsModule, Aviso, Boton, Campo, EstadoVacio, InsigniaEstado, Tarjeta],
  templateUrl: './catalogo.html',
  styleUrl: './catalogo.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaCatalogo {
  private readonly http = inject(HttpClient);
  protected readonly pesos = formatoPesos;
  protected readonly servicios = signal<Servicio[] | null>(null);
  protected readonly repuestos = signal<Repuesto[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly exito = signal<string | null>(null);

  protected readonly seleccion = signal<Servicio | 'nuevo' | null>(null);
  protected form = { code: '', name: '', labor_price: 0, duration_min: 60, active: true };
  protected readonly errorForm = signal<string | null>(null);
  protected readonly camposError = signal<string[]>([]);
  protected readonly guardando = signal(false);

  protected readonly lineas = signal<LineaRepuesto[]>([]);
  protected agregarId: number | null = null;
  protected agregarCantidad = 1;
  protected readonly errorLineas = signal<string | null>(null);
  protected readonly guardandoLineas = signal(false);
  protected readonly disponibles = computed(() =>
    this.repuestos().filter((r) => r.active && !this.lineas().some((l) => l.part_id === r.id)));

  constructor() {
    this.cargar();
    this.http.get<Repuesto[]>('/api/inventario/repuestos').subscribe({ next: (r) => this.repuestos.set(r) });
  }

  protected cargar(): void {
    this.error.set(null);
    this.http.get<Servicio[]>('/api/catalogo/servicios', { params: { todos: true } }).subscribe({
      next: (s) => this.servicios.set(s),
      error: (e: unknown) => this.error.set(mensajeError(e, ERROR_INTERNO)),
    });
  }

  protected abrir(s: Servicio | 'nuevo'): void {
    this.errorForm.set(null);
    this.errorLineas.set(null);
    this.camposError.set([]);
    this.exito.set(null);
    this.form = s === 'nuevo' ? { code: '', name: '', labor_price: 0, duration_min: 60, active: true }
      : { code: s.code, name: s.name, labor_price: s.labor_price, duration_min: s.duration_min, active: s.active };
    this.lineas.set(s === 'nuevo' ? [] : s.repuestos.map((l) => ({ ...l })));
    this.seleccion.set(s);
  }

  protected guardar(): void {
    const s = this.seleccion();
    if (!s) return;
    const { code, ...cambios } = this.form;
    const peticion = s === 'nuevo'
      ? this.http.post<Servicio>('/api/catalogo/servicios', this.form)
      : this.http.patch<Servicio>(`/api/catalogo/servicios/${s.id}`, cambios);
    this.guardando.set(true);
    this.errorForm.set(null);
    peticion.subscribe({
      next: (r) => {
        this.guardando.set(false);
        this.exito.set(`Servicio ${code || r.code} guardado.`);
        this.seleccion.set(r);
        this.cargar();
      },
      error: (e: unknown) => {
        this.guardando.set(false);
        this.camposError.set(camposConError(e));
        this.errorForm.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }

  protected agregar(): void {
    const r = this.repuestos().find((x) => x.id === this.agregarId);
    if (!r) return;
    if (this.agregarCantidad <= 0) {
      this.errorLineas.set('La cantidad debe ser mayor a cero');
      return;
    }
    this.lineas.update((ls) => [...ls, { part_id: r.id, sku: r.sku, name: r.name, quantity: this.agregarCantidad, available: r.available }]);
    this.agregarId = null;
    this.agregarCantidad = 1;
  }

  protected quitar(id: number): void {
    this.lineas.update((ls) => ls.filter((l) => l.part_id !== id));
  }

  protected cambiarCantidad(id: number, cantidad: number): void {
    this.lineas.update((ls) => ls.map((l) => (l.part_id === id ? { ...l, quantity: Number(cantidad) } : l)));
  }

  protected guardarLineas(): void {
    const s = this.seleccion();
    if (!s || s === 'nuevo') return;
    this.guardandoLineas.set(true);
    this.errorLineas.set(null);
    this.http.put<Servicio>(`/api/catalogo/servicios/${s.id}/repuestos`,
      this.lineas().map((l) => ({ part_id: l.part_id, quantity: l.quantity }))).subscribe({
      next: (r) => {
        this.guardandoLineas.set(false);
        this.exito.set(r.advertencia ? `Repuestos guardados. ${r.advertencia}.` : 'Repuestos guardados. Aplican a las citas futuras.');
        this.seleccion.set(r);
        this.lineas.set(r.repuestos.map((l) => ({ ...l })));
        this.cargar();
      },
      error: (e: unknown) => {
        this.guardandoLineas.set(false);
        this.errorLineas.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }
}
