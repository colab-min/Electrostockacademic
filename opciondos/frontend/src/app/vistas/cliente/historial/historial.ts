import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { EspacioFotos } from '../../../componentes/espacio-fotos/espacio-fotos';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { TIPOS_VEHICULO } from '../../../componentes/formulario-vehiculo/formulario-vehiculo';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { formatoFecha, formatoPesos } from '../../../core/formato';

interface Orden {
  id: number;
  number: string;
  created_at: string;
  delivered_at: string | null;
  services: string[];
  parts: { sku: string; name: string; quantity: number }[];
  total_paid: number | null;
}

interface Historial {
  vehicle: { id: number; type: string; serial_number: string; plate: string | null; brand: string; model: string };
  orders: Orden[];
  page: number;
  has_more: boolean;
}

/** CL-08 Historial del vehículo (HU-30): órdenes entregadas, 20 por página; un vehículo ajeno no existe (RN-46). */
@Component({
  selector: 'app-vista-historial',
  imports: [RouterLink, Aviso, Boton, EspacioFotos, EstadoVacio, Tarjeta],
  templateUrl: './historial.html',
  styleUrl: './historial.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaHistorial {
  private readonly http = inject(HttpClient);
  readonly id = input.required<string>();
  protected readonly tipos = TIPOS_VEHICULO;
  protected readonly fecha = formatoFecha;
  protected readonly pesos = formatoPesos;

  protected readonly datos = signal<Historial | null>(null);
  protected readonly ordenes = signal<Orden[]>([]);
  protected readonly cargando = signal(false);
  protected readonly noEncontrado = signal(false);
  protected readonly error = signal<string | null>(null);

  constructor() {
    effect(() => this.cargar(this.id(), 1));
  }

  protected cargar(id: string, pagina: number): void {
    this.cargando.set(true);
    this.error.set(null);
    this.http.get<Historial>(`/api/clientes/mis-vehiculos/${encodeURIComponent(id)}/historial`, { params: { pagina } }).subscribe({
      next: (h) => {
        this.cargando.set(false);
        this.datos.set(h);
        this.ordenes.set(pagina === 1 ? h.orders : [...this.ordenes(), ...h.orders]);
      },
      error: (e: unknown) => {
        this.cargando.set(false);
        if (e instanceof HttpErrorResponse && (e.status === 404 || e.status === 422)) this.noEncontrado.set(true);
        else this.error.set('No fue posible cargar el historial en este momento, por favor intenta nuevamente');
      },
    });
  }

  protected masAntiguas(): void {
    const d = this.datos();
    if (d) this.cargar(this.id(), d.page + 1);
  }
}
