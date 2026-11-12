import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { CalendarioMes, EstadoDia } from '../../../componentes/calendario-mes/calendario-mes';
import { Campo } from '../../../componentes/campo/campo';
import { DialogoConfirmacion } from '../../../componentes/dialogo-confirmacion/dialogo-confirmacion';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoFecha, formatoFechaHora } from '../../../core/formato';

interface FranjaRecepcion {
  id: number;
  hora: string;
  capacidad: number;
  ocupados: number;
  bloqueada: boolean;
  motivo: string | null;
  semaforo: 'verde' | 'amarillo' | 'rojo';
  etiqueta: string;
  citas: { id: number; code: string; status: string; cliente: string; vehiculo: string; servicio: string }[];
}

interface Calendario {
  fecha: string;
  franjas: FranjaRecepcion[];
  recordatorios: { id: number; code: string; starts_at: string; status: string; sent_at: string | null }[];
}

const ERROR_INTERNO = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** SE-01 Agenda y capacidad (HU-02) con los recordatorios simulados (HU-12). */
@Component({
  selector: 'app-vista-agenda-capacidad',
  imports: [FormsModule, Aviso, Boton, CalendarioMes, Campo, DialogoConfirmacion, EstadoVacio, InsigniaEstado, Tarjeta],
  templateUrl: './agenda-capacidad.html',
  styleUrl: './agenda-capacidad.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaAgendaCapacidad {
  private readonly http = inject(HttpClient);
  protected readonly fecha = signal(iso(new Date()));
  protected readonly mes = signal(`${iso(new Date()).slice(0, 7)}-01`);
  protected readonly datos = signal<Calendario | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly aBloquear = signal<FranjaRecepcion | null>(null);
  protected readonly errorBloqueo = signal<string | null>(null);
  protected readonly procesando = signal(false);
  protected motivo = '';
  protected readonly fechaLarga = formatoFecha;
  protected readonly fechaHora = formatoFechaHora;

  /** Lunes a sábado se pueden consultar; el domingo el taller cierra (RN-01). */
  protected readonly dias = computed(() => {
    const [y, m] = this.mes().split('-').map(Number);
    const out: Record<string, EstadoDia> = {};
    for (let d = 1; d <= new Date(y, m, 0).getDate(); d++) {
      const f = new Date(y, m - 1, d);
      out[iso(f)] = f.getDay() === 0 ? 'cerrado' : 'disponible';
    }
    return out;
  });

  constructor() {
    this.cargar();
  }

  protected elegir(fecha: string): void {
    this.fecha.set(fecha);
    this.cargar();
  }

  protected cargar(): void {
    this.error.set(null);
    this.http.get<Calendario>('/api/agenda/calendario', { params: { fecha: this.fecha() } }).subscribe({
      next: (d) => this.datos.set(d),
      error: (e: unknown) => {
        this.datos.set(null);
        this.error.set(mensajeError(e, ERROR_INTERNO));
      },
    });
  }

  protected abrirBloqueo(f: FranjaRecepcion): void {
    this.motivo = '';
    this.errorBloqueo.set(null);
    this.aBloquear.set(f);
  }

  protected bloquear(): void {
    const f = this.aBloquear();
    if (!f) return;
    if (!this.motivo.trim()) {
      this.errorBloqueo.set('Indique el motivo del bloqueo');
      return;
    }
    this.enviar(f, true, () => this.aBloquear.set(null), (m) => this.errorBloqueo.set(m));
  }

  protected desbloquear(f: FranjaRecepcion): void {
    this.enviar(f, false, () => undefined, (m) => this.error.set(m));
  }

  private enviar(f: FranjaRecepcion, bloquear: boolean, ok: () => void, falla: (m: string) => void): void {
    this.procesando.set(true);
    this.http.post(`/api/agenda/franjas/${f.id}/bloqueo`, { bloquear, motivo: bloquear ? this.motivo : null }).subscribe({
      next: () => {
        this.procesando.set(false);
        ok();
        this.cargar();
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        falla(mensajeError(e, ERROR_INTERNO));
      },
    });
  }
}
