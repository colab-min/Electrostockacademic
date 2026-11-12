import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { CabeceraVista } from '../../../componentes/cabecera-vista/cabecera-vista';
import { Esqueleto } from '../../../componentes/esqueleto/esqueleto';
import { Icono } from '../../../componentes/icono/icono';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { CalendarioMes, EstadoDia } from '../../../componentes/calendario-mes/calendario-mes';
import { Campo } from '../../../componentes/campo/campo';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { FranjaHoraria } from '../../../componentes/franja-horaria/franja-horaria';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoFecha, formatoFechaHora, formatoPesos } from '../../../core/formato';
import { Cita, Franja, textoLimite } from './cita';

interface Vehiculo {
  id: number;
  serial_number: string;
  brand: string;
  model: string;
  nominal_voltage_v: number;
}

interface Servicio {
  id: number;
  name: string;
  labor_price: number;
  duration_min: number;
  repuestos: { part_id: number; name: string; quantity: number; available: number; compatible_voltage_v: number | null }[];
}

const RETENCION_S = 5 * 60;

function mesDe(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
}

/** CL-02 a CL-05: asistente de 4 pasos para agendar (HU-01, HU-19). */
@Component({
  selector: 'app-vista-agendar',
  imports: [FormsModule, RouterLink, Aviso, Boton, CabeceraVista, CalendarioMes, Campo, Esqueleto, EstadoVacio, FranjaHoraria, Icono, Tarjeta],
  templateUrl: './agendar.html',
  styleUrl: './agendar.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaAgendar {
  private readonly http = inject(HttpClient);
  protected readonly pasos = ['Vehículo y servicio', 'Día', 'Hora', 'Confirmar'];
  protected readonly pasosCortos = ['Vehículo', 'Día', 'Hora', 'Confirmar'];
  /** Títulos de los marcos CL-02 a CL-05 de makups3. */
  protected readonly titulos = ['vehículo y servicio', 'elegir el día', 'elegir la hora', 'confirmar'];
  protected readonly paso = signal(1);
  protected readonly retencion = RETENCION_S;
  protected readonly vehiculos = signal<Vehiculo[] | null>(null);
  protected readonly servicios = signal<Servicio[]>([]);
  protected readonly vehiculoId = signal<number | null>(null);
  protected readonly servicioId = signal<number | null>(null);
  protected motivoVoltaje = '';
  protected readonly mes = signal(mesDe(new Date()));
  protected readonly dias = signal<Record<string, EstadoDia> | null>(null);
  protected readonly fecha = signal<string | null>(null);
  protected readonly franjas = signal<Franja[] | null>(null);
  protected readonly cita = signal<Cita | null>(null);
  protected readonly confirmada = signal(false);
  protected readonly expirada = signal(false);
  protected readonly restante = signal(RETENCION_S);
  protected readonly procesando = signal(false);
  protected readonly error = signal<string | null>(null);
  private reloj: ReturnType<typeof setInterval> | null = null;

  protected readonly pesos = formatoPesos;
  protected readonly fechaLarga = formatoFecha;
  protected readonly fechaHora = formatoFechaHora;
  protected readonly limite = textoLimite;

  protected readonly vehiculo = computed(() => this.vehiculos()?.find((v) => v.id === this.vehiculoId()) ?? null);
  protected readonly servicio = computed(() => this.servicios().find((s) => s.id === this.servicioId()) ?? null);
  protected readonly faltante = computed(() => {
    const r = this.servicio()?.repuestos.find((p) => p.available < p.quantity);
    return r ? `No tenemos ${r.name} disponible para este servicio en este momento.` : null;
  });
  protected readonly riesgoVoltaje = computed(() => {
    const v = this.vehiculo();
    const r = this.servicio()?.repuestos.find((p) => v && p.compatible_voltage_v && p.compatible_voltage_v !== v.nominal_voltage_v);
    return v && r ? `Riesgo eléctrico: ${r.name} es de ${r.compatible_voltage_v} V y tu vehículo es de ${v.nominal_voltage_v} V. Indica un motivo para continuar.` : null;
  });
  protected readonly mesSinCupo = computed(() => {
    const d = this.dias();
    return d !== null && !Object.values(d).includes('disponible');
  });
  protected readonly diaSinCupo = computed(() => this.franjas()?.every((f) => f.estado !== 'libre') ?? false);
  protected readonly contador = computed(() => {
    const s = this.restante();
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  });

  constructor() {
    this.http.get<Vehiculo[]>('/api/clientes/mis-vehiculos').subscribe({
      next: (v) => this.vehiculos.set(v),
      error: (e: unknown) => this.error.set(mensajeError(e)),
    });
    this.http.get<Servicio[]>('/api/catalogo/servicios').subscribe({
      next: (s) => this.servicios.set(s),
      error: (e: unknown) => this.error.set(mensajeError(e)),
    });
    inject(DestroyRef).onDestroy(() => this.pararReloj());
  }

  protected irAPaso(n: number): void {
    this.error.set(null);
    this.paso.set(n);
    if (n === 2) this.cargarMes(this.mes());
  }

  protected cargarMes(mes: string): void {
    const id = this.servicioId();
    if (!id) return;
    this.mes.set(mes);
    this.dias.set(null);
    this.http.get<{ dias: Record<string, EstadoDia> }>('/api/agenda/disponibilidad', { params: { service_id: id, mes: mes.slice(0, 7) } })
      .subscribe({ next: (r) => this.dias.set(r.dias), error: (e: unknown) => this.error.set(mensajeError(e)) });
  }

  protected elegirDia(fecha: string): void {
    this.fecha.set(fecha);
    this.irAPaso(3);
    this.cargarFranjas();
  }

  private cargarFranjas(): void {
    this.franjas.set(null);
    this.http.get<Franja[]>('/api/agenda/franjas', { params: { service_id: this.servicioId()!, fecha: this.fecha()! } })
      .subscribe({ next: (f) => this.franjas.set(f), error: (e: unknown) => this.error.set(mensajeError(e)) });
  }

  /** Elegir la hora crea la cita En Proceso y aparta cupo y repuestos por 5 minutos. */
  protected elegirHora(f: Franja): void {
    if (this.procesando()) return;
    this.procesando.set(true);
    this.error.set(null);
    const body = {
      vehicle_id: this.vehiculoId(), service_id: this.servicioId(), fecha: this.fecha(), hora: f.hora,
      motivo_voltaje: this.riesgoVoltaje() ? this.motivoVoltaje : null,
    };
    this.http.post<Cita>('/api/agenda/citas', body).subscribe({
      next: (c) => {
        this.procesando.set(false);
        this.cita.set(c);
        this.expirada.set(false);
        this.paso.set(4);
        this.iniciarReloj();
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        this.error.set(mensajeError(e, 'No fue posible completar la reserva, intenta de nuevo'));
        this.cargarFranjas();
      },
    });
  }

  protected confirmar(): void {
    const c = this.cita();
    if (!c) return;
    this.procesando.set(true);
    this.error.set(null);
    this.http.post<Cita>(`/api/agenda/citas/${c.id}/confirmar`, null).subscribe({
      next: (r) => {
        this.procesando.set(false);
        this.pararReloj();
        this.cita.set(r);
        this.confirmada.set(true);
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        if (e instanceof HttpErrorResponse && e.status === 410) this.marcarExpirada();
        else this.error.set(mensajeError(e, 'No fue posible completar la reserva, intenta de nuevo'));
      },
    });
  }

  /** "Cancelar" en el paso 4 abandona el asistente y libera todo de inmediato (RN-19). */
  protected abandonar(): void {
    const c = this.cita();
    if (!c) return;
    this.procesando.set(true);
    this.http.post<Cita>(`/api/agenda/citas/${c.id}/cancelar`, null).subscribe({
      next: () => this.reiniciarHora(),
      error: () => this.reiniciarHora(),
    });
  }

  protected reiniciarHora(): void {
    this.procesando.set(false);
    this.pararReloj();
    this.cita.set(null);
    this.expirada.set(false);
    this.irAPaso(3);
    this.cargarFranjas();
  }

  private iniciarReloj(): void {
    this.pararReloj();
    const fin = Date.now() + RETENCION_S * 1000;
    this.restante.set(RETENCION_S);
    this.reloj = setInterval(() => {
      const s = Math.max(0, Math.round((fin - Date.now()) / 1000));
      this.restante.set(s);
      if (s === 0) this.marcarExpirada();
    }, 1000);
  }

  private marcarExpirada(): void {
    this.pararReloj();
    this.expirada.set(true);
  }

  private pararReloj(): void {
    if (this.reloj) clearInterval(this.reloj);
    this.reloj = null;
  }
}
