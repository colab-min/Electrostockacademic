import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { switchMap, timer } from 'rxjs';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { BuscadorVehiculo } from '../../../componentes/buscador-vehiculo/buscador-vehiculo';
import { Campo } from '../../../componentes/campo/campo';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoFechaHora } from '../../../core/formato';

interface Vehiculo {
  id: number;
  type: string;
  serial_number: string;
  plate: string | null;
  brand: string;
  model: string;
  customer: { full_name: string; document_type: string; document_number: string };
}
interface Falla { id: number; name: string; priority: string; estimated_minutes: number }
interface Servicio { id: number; name: string; duration_min: number; active: boolean }
interface EnCola {
  id: number;
  number: string;
  priority: string | null;
  fault_name: string | null;
  queue_position: number;
  hora_estimada: string | null;
  vehicle: { brand: string; model: string; serial_number: string };
}
interface Ingreso {
  number: string;
  tracking_code: string;
  queue_position: number | null;
  estimated_delivery_at: string | null;
  hora_estimada: string | null;
}

const ERROR_INTERNO = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';

/** SE-02 Ingreso sin cita (HU-03 con la clasificación de HU-04). La cola se refresca cada 3 s. */
@Component({
  selector: 'app-vista-ingreso-sin-cita',
  imports: [FormsModule, RouterLink, Aviso, Boton, BuscadorVehiculo, Campo, EstadoVacio, InsigniaEstado, Tarjeta],
  templateUrl: './ingreso-sin-cita.html',
  styleUrl: './ingreso-sin-cita.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaIngresoSinCita implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly vehiculos = signal<Vehiculo[] | null>(null);
  protected readonly elegido = signal<Vehiculo | null>(null);
  protected readonly fallas = signal<Falla[]>([]);
  protected readonly servicios = signal<Servicio[]>([]);
  protected readonly errorCatalogo = signal<string | null>(null);
  protected readonly cola = signal<EnCola[] | null>(null);
  protected readonly resultado = signal<Ingreso | null>(null);
  protected readonly copiado = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly buscando = signal(false);
  protected readonly procesando = signal(false);
  protected readonly fecha = formatoFechaHora;
  protected fallaId: number | null = null;
  protected servicioId: number | null = null;
  protected motivo = '';
  protected intentado = false;

  constructor() {
    timer(0, 3000)
      .pipe(switchMap(() => this.http.get<EnCola[]>('/api/ordenes/cola')), takeUntilDestroyed())
      .subscribe({ next: (c) => this.cola.set(c), error: (e: unknown) => this.error.set(mensajeError(e, ERROR_INTERNO)) });
  }

  ngOnInit(): void {
    this.http.get<Falla[]>('/api/catalogo/fallas').subscribe({
      next: (f) => this.fallas.set(f),
      error: (e: unknown) => this.errorCatalogo.set(mensajeError(e, ERROR_INTERNO)),
    });
    this.http.get<Servicio[]>('/api/catalogo/servicios').subscribe({
      next: (s) => this.servicios.set(s.filter((x) => x.active)),
      error: (e: unknown) => this.errorCatalogo.set(mensajeError(e, ERROR_INTERNO)),
    });
  }

  protected buscar(q: string): void {
    this.buscando.set(true);
    this.elegido.set(null);
    this.http.get<Vehiculo[]>('/api/clientes/vehiculos', { params: { q } }).subscribe({
      next: (v) => {
        this.buscando.set(false);
        this.vehiculos.set(v);
        if (v.length === 1) this.elegido.set(v[0]);
      },
      error: (e: unknown) => {
        this.buscando.set(false);
        this.error.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }

  protected registrar(): void {
    this.intentado = true;
    const v = this.elegido();
    if (!v || !this.fallaId || !this.servicioId) return;
    this.procesando.set(true);
    this.error.set(null);
    this.http.post<Ingreso>('/api/ordenes/ingreso', {
      vehicle_id: v.id, fault_type_id: Number(this.fallaId), service_id: Number(this.servicioId),
      intake_reason: this.motivo.trim() || null,
    }).subscribe({
      next: (r) => {
        this.procesando.set(false);
        this.resultado.set(r);
        this.copiado.set(false);
        this.elegido.set(null);
        this.vehiculos.set(null);
        this.fallaId = this.servicioId = null;
        this.motivo = '';
        this.intentado = false;
        this.http.get<EnCola[]>('/api/ordenes/cola').subscribe((c) => this.cola.set(c));
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        this.error.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }

  protected copiar(codigo: string): void {
    void navigator.clipboard?.writeText(codigo).then(() => this.copiado.set(true));
  }
}
