import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { CalendarioMes, EstadoDia } from '../../../componentes/calendario-mes/calendario-mes';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { FranjaHoraria } from '../../../componentes/franja-horaria/franja-horaria';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoFecha, formatoFechaHora } from '../../../core/formato';
import { Cita, FUERA_VENTANA, Franja, textoLimite } from '../agendar/cita';

/** CL-06 Reprogramar cita (HU-11): nuevas franjas en una transacción; los repuestos se conservan. */
@Component({
  selector: 'app-vista-reprogramar',
  imports: [RouterLink, Aviso, Boton, CalendarioMes, EstadoVacio, FranjaHoraria, Tarjeta],
  templateUrl: './reprogramar.html',
  styleUrl: './reprogramar.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaReprogramar implements OnInit {
  private readonly http = inject(HttpClient);
  readonly id = input.required<string>();
  protected readonly cita = signal<Cita | null>(null);
  protected readonly noEncontrada = signal(false);
  protected readonly mes = signal('');
  protected readonly dias = signal<Record<string, EstadoDia>>({});
  protected readonly fecha = signal<string | null>(null);
  protected readonly franjas = signal<Franja[] | null>(null);
  protected readonly hora = signal<string | null>(null);
  protected readonly procesando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly hecha = signal(false);
  protected readonly fueraVentana = FUERA_VENTANA;
  protected readonly fechaHora = formatoFechaHora;
  protected readonly fechaLarga = formatoFecha;
  protected readonly limite = textoLimite;
  protected readonly sinHora = computed(() => this.franjas()?.every((f) => f.estado !== 'libre') ?? false);

  ngOnInit(): void {
    this.http.get<Cita[]>('/api/agenda/citas/mias').subscribe({
      next: (lista) => {
        const c = lista.find((x) => String(x.id) === this.id());
        if (!c) {
          this.noEncontrada.set(true);
          return;
        }
        this.cita.set(c);
        this.cargarMes(`${c.starts_at.slice(0, 7)}-01`);
      },
      error: (e: unknown) => this.error.set(mensajeError(e)),
    });
  }

  protected cargarMes(mes: string): void {
    this.mes.set(mes);
    this.http.get<{ dias: Record<string, EstadoDia> }>('/api/agenda/disponibilidad',
      { params: { service_id: this.cita()!.service.id, mes: mes.slice(0, 7) } })
      .subscribe({ next: (r) => this.dias.set(r.dias), error: (e: unknown) => this.error.set(mensajeError(e)) });
  }

  protected elegirDia(fecha: string): void {
    this.fecha.set(fecha);
    this.hora.set(null);
    this.cargarFranjas();
  }

  private cargarFranjas(): void {
    this.franjas.set(null);
    this.http.get<Franja[]>('/api/agenda/franjas', { params: { service_id: this.cita()!.service.id, fecha: this.fecha()! } })
      .subscribe({ next: (f) => this.franjas.set(f), error: (e: unknown) => this.error.set(mensajeError(e)) });
  }

  protected confirmar(): void {
    this.procesando.set(true);
    this.error.set(null);
    this.http.post<Cita>(`/api/agenda/citas/${this.id()}/reprogramar`, { fecha: this.fecha(), hora: this.hora() }).subscribe({
      next: (c) => {
        this.procesando.set(false);
        this.cita.set(c);
        this.hecha.set(true);
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        this.error.set(mensajeError(e));
        this.hora.set(null);
        this.cargarFranjas();
      },
    });
  }
}
