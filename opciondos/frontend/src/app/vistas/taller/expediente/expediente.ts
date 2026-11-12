import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, ElementRef, computed, effect, inject, input, signal, viewChild } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { BuscadorVehiculo } from '../../../componentes/buscador-vehiculo/buscador-vehiculo';
import { EspacioFotos } from '../../../componentes/espacio-fotos/espacio-fotos';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { TIPOS_VEHICULO } from '../../../componentes/formulario-vehiculo/formulario-vehiculo';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoFechaHora } from '../../../core/formato';
import { SesionService } from '../../../core/sesion.service';

interface Coincidencia {
  id: number;
  type: string;
  serial_number: string;
  plate: string | null;
  brand: string;
  model: string;
  customer: { full_name: string; document_type: string; document_number: string };
}

interface Nota { id: number; content_html: string; author: string; created_at: string }

interface Expediente {
  vehicle: Coincidencia & { year: number; nominal_voltage_v: number; battery_capacity_ah: number; battery_cell: string | null;
    power_w: number | null; controller: string | null };
  customer: { full_name: string; document_type: string; document_number: string };
  orders: { id: number; number: string; status: string; created_at: string; delivered_at: string | null; intake_reason: string;
    diagnosis: string | null; services: string[]; parts: { sku: string; name: string; quantity: number }[] }[];
  notes: Nota[];
}

const NO_ENCONTRADO = 'No se encontró un vehículo con esa serie, placa o documento.';
const ERROR_SERVIDOR = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';

/** ME-03 Expediente técnico (HU-06): búsqueda, ficha, órdenes y notas. La secretaria y el admin solo leen. */
@Component({
  selector: 'app-vista-expediente',
  imports: [RouterLink, Aviso, Boton, BuscadorVehiculo, EspacioFotos, EstadoVacio, InsigniaEstado, Tarjeta],
  templateUrl: './expediente.html',
  styleUrl: './expediente.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaExpediente {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly sesion = inject(SesionService);
  private readonly editor = viewChild<ElementRef<HTMLDivElement>>('editor');

  readonly serie = input<string>();
  protected readonly tipos = TIPOS_VEHICULO;
  protected readonly fecha = formatoFechaHora;
  protected readonly puedeAnotar = computed(() => this.sesion.rol() === 'MECHANIC');

  protected readonly buscando = signal(false);
  protected readonly cargando = signal(false);
  protected readonly coincidencias = signal<Coincidencia[] | null>(null);
  protected readonly expediente = signal<Expediente | null>(null);
  protected readonly noEncontrado = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly guardando = signal(false);
  protected readonly errorNota = signal<string | null>(null);
  protected readonly mensajeNoEncontrado = NO_ENCONTRADO;

  constructor() {
    effect(() => {
      const serie = this.serie();
      if (serie) this.cargar(serie);
    });
  }

  protected buscar(q: string): void {
    this.buscando.set(true);
    this.error.set(null);
    this.noEncontrado.set(false);
    this.coincidencias.set(null);
    this.http.get<Coincidencia[]>('/api/clientes/vehiculos', { params: { q } }).subscribe({
      next: (lista) => {
        this.buscando.set(false);
        if (lista.length === 1) void this.router.navigate(['/taller/vehiculos', lista[0].serial_number]);
        else if (lista.length === 0) {
          this.expediente.set(null);
          this.noEncontrado.set(true);
        } else {
          this.expediente.set(null);
          this.coincidencias.set(lista);
        }
      },
      error: (e: unknown) => {
        this.buscando.set(false);
        this.error.set(mensajeError(e, ERROR_SERVIDOR));
      },
    });
  }

  protected cargar(serie: string): void {
    this.cargando.set(true);
    this.error.set(null);
    this.noEncontrado.set(false);
    this.coincidencias.set(null);
    this.http.get<Expediente>(`/api/clientes/vehiculos/${encodeURIComponent(serie)}/expediente`).subscribe({
      next: (exp) => {
        this.cargando.set(false);
        this.expediente.set(exp);
      },
      error: (e: unknown) => {
        this.cargando.set(false);
        this.expediente.set(null);
        if (e instanceof HttpErrorResponse && e.status === 404) this.noEncontrado.set(true);
        else this.error.set(mensajeError(e, ERROR_SERVIDOR));
      },
    });
  }

  /** Formato básico del editor: negrita y viñetas (execCommand basta para la demo). */
  protected formato(comando: 'bold' | 'insertUnorderedList'): void {
    this.editor()?.nativeElement.focus();
    document.execCommand(comando);
  }

  protected guardarNota(): void {
    const exp = this.expediente();
    const editor = this.editor()?.nativeElement;
    if (!exp || !editor) return;
    if (!editor.textContent?.trim()) {
      this.errorNota.set('Escriba el contenido de la nota.');
      return;
    }
    this.guardando.set(true);
    this.errorNota.set(null);
    this.http.post<Nota>(`/api/clientes/vehiculos/${exp.vehicle.id}/notas`, { content_html: editor.innerHTML }).subscribe({
      next: (nota) => {
        this.guardando.set(false);
        editor.innerHTML = '';
        this.expediente.set({ ...exp, notes: [nota, ...exp.notes] });
      },
      error: (e: unknown) => {
        this.guardando.set(false);
        this.errorNota.set(mensajeError(e, ERROR_SERVIDOR));
      },
    });
  }
}
