import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Observable, forkJoin } from 'rxjs';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { Campo } from '../../../componentes/campo/campo';
import { EspacioFotos } from '../../../componentes/espacio-fotos/espacio-fotos';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { EventoLinea, LineaTiempo } from '../../../componentes/linea-tiempo/linea-tiempo';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoFechaHora, formatoPesos } from '../../../core/formato';

interface Detalle {
  id: number;
  number: string;
  status: string;
  priority: string | null;
  intake_reason: string;
  diagnosis: string | null;
  version: number;
  estimated_delivery_at: string | null;
  vehicle: { type_label: string; brand: string; model: string; serial_number: string; nominal_voltage_v: number };
  service_lines: { service_id: number; name: string; applied_price: number }[];
  parts: { id: number; sku: string; name: string; quantity: number; unit_price: number; status: string }[];
  history: { label: string; user_name: string | null; reason: string | null; created_at: string }[];
}
interface Transicion { to_status: string; label: string }
interface Repuesto { id: number; sku: string; name: string; available: number; active?: boolean }
interface Servicio { id: number; name: string; active: boolean }

const ERROR_INTERNO = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';
const EDITABLES = ['DIAGNOSING', 'WAITING_PARTS', 'REPAIRING'];

/** ME-02 Detalle de orden (HU-05, HU-09, HU-25). Una orden ajena llega como no encontrada. */
@Component({
  selector: 'app-vista-detalle-orden',
  imports: [FormsModule, RouterLink, Aviso, Boton, Campo, EspacioFotos, InsigniaEstado, LineaTiempo, Tarjeta],
  templateUrl: './detalle-orden.html',
  styleUrl: './detalle-orden.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaDetalleOrden implements OnInit {
  readonly id = input.required<string>();
  private readonly http = inject(HttpClient);

  protected readonly orden = signal<Detalle | null>(null);
  protected readonly transiciones = signal<Transicion[]>([]);
  protected readonly repuestos = signal<Repuesto[]>([]);
  protected readonly servicios = signal<Servicio[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly errorRepuesto = signal<string | null>(null);
  protected readonly exito = signal<string | null>(null);
  protected readonly procesando = signal<string | null>(null);
  protected readonly pesos = formatoPesos;
  protected readonly fecha = formatoFechaHora;

  protected diagnostico = '';
  protected motivo = '';
  protected repuestoId: number | null = null;
  protected cantidad = 1;
  protected motivoVoltaje = '';
  protected servicioId: number | null = null;

  protected readonly editable = computed(() => EDITABLES.includes(this.orden()?.status ?? ''));
  protected readonly eventos = computed<EventoLinea[]>(() => (this.orden()?.history ?? []).map((h) => ({
    titulo: h.label, fecha: h.created_at, detalle: [h.user_name, h.reason].filter(Boolean).join(' · ') || null,
  })));
  protected readonly pideMotivo = computed(() => this.transiciones().some((t) => t.to_status === 'PENDING_INSTALLATION'));

  ngOnInit(): void {
    this.cargar();
    this.http.get<Repuesto[]>('/api/inventario/repuestos').subscribe({
      next: (r) => this.repuestos.set(r.filter((p) => p.active !== false)),
      error: () => this.repuestos.set([]),
    });
    this.http.get<Servicio[]>('/api/catalogo/servicios').subscribe({
      next: (s) => this.servicios.set(s.filter((x) => x.active)),
      error: () => this.servicios.set([]),
    });
  }

  private cargar(): void {
    forkJoin([
      this.http.get<Detalle>(`/api/ordenes/${this.id()}`),
      this.http.get<Transicion[]>(`/api/ordenes/${this.id()}/transiciones`),
    ]).subscribe({
      next: ([o, t]) => this.mostrar(o, t),
      error: (e: unknown) => this.error.set(mensajeError(e, ERROR_INTERNO)),
    });
  }

  private mostrar(o: Detalle, t?: Transicion[]): void {
    this.orden.set(o);
    this.diagnostico = o.diagnosis ?? '';
    if (t) this.transiciones.set(t);
    else this.http.get<Transicion[]>(`/api/ordenes/${o.id}/transiciones`).subscribe((x) => this.transiciones.set(x));
  }

  /** Ejecuta una acción que devuelve el detalle actualizado. */
  private accion(clave: string, peticion: Observable<Detalle>, exito: string, alError = this.error): void {
    this.procesando.set(clave);
    this.error.set(null);
    this.errorRepuesto.set(null);
    this.exito.set(null);
    peticion.subscribe({
      next: (o) => {
        this.procesando.set(null);
        this.exito.set(exito);
        this.mostrar(o);
      },
      error: (e: unknown) => {
        this.procesando.set(null);
        alError.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }

  protected cambiar(t: Transicion): void {
    const o = this.orden();
    if (!o) return;
    const reason = t.to_status === 'PENDING_INSTALLATION' ? this.motivo.trim() : null;
    this.accion(t.to_status, this.http.post<Detalle>(`/api/ordenes/${o.id}/estado`,
      { to_status: t.to_status, version: o.version, reason }), `La orden pasó a ${t.label}.`);
  }

  protected guardarDiagnostico(): void {
    const o = this.orden();
    if (!o || !this.diagnostico.trim()) return;
    this.accion('diagnostico', this.http.patch<Detalle>(`/api/ordenes/${o.id}/diagnostico`,
      { diagnosis: this.diagnostico, version: o.version }), 'Diagnóstico guardado.');
  }

  protected agregarRepuesto(): void {
    const o = this.orden();
    if (!o || !this.repuestoId) return;
    this.accion('repuesto', this.http.post<Detalle>(`/api/ordenes/${o.id}/repuestos`, {
      part_id: Number(this.repuestoId), quantity: this.cantidad, voltage_reason: this.motivoVoltaje.trim() || null,
    }), 'Repuesto reservado.', this.errorRepuesto);
  }

  protected linea(lineaId: number, verbo: 'instalar' | 'retirar'): void {
    const o = this.orden();
    if (!o) return;
    this.accion(`${verbo}-${lineaId}`, this.http.post<Detalle>(`/api/ordenes/${o.id}/repuestos/${lineaId}/${verbo}`, {}),
      verbo === 'instalar' ? 'Repuesto instalado.' : 'Repuesto retirado.', this.errorRepuesto);
  }

  protected agregarServicio(): void {
    const o = this.orden();
    if (!o || !this.servicioId) return;
    this.accion('servicio', this.http.post<Detalle>(`/api/ordenes/${o.id}/servicios`,
      { service_id: Number(this.servicioId) }), 'Servicio agregado.');
  }
}
