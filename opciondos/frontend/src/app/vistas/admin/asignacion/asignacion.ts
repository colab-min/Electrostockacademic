import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { EstadoVacio } from '../../../componentes/estado-vacio/estado-vacio';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoFechaHora } from '../../../core/formato';

interface Orden {
  id: number;
  number: string;
  status: string;
  priority: string | null;
  version: number;
  intake_reason: string;
  created_at: string;
  mechanic_id: number | null;
  mechanic_name: string | null;
  vehicle: { brand: string; model: string };
}
interface Mecanico { id: number; full_name: string; active: boolean }

const ERROR_INTERNO = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';
const TECNICOS = ['ASSIGNED', 'DIAGNOSING', 'WAITING_PARTS', 'REPAIRING'];

/** AD-02 Asignación de mecánicos (HU-24): Ingresadas por prioridad y llegada, y reasignación de las técnicas. */
@Component({
  selector: 'app-vista-asignacion',
  imports: [NgTemplateOutlet, FormsModule, Aviso, Boton, EstadoVacio, InsigniaEstado, Tarjeta],
  templateUrl: './asignacion.html',
  styleUrl: './asignacion.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaAsignacion implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly ordenes = signal<Orden[] | null>(null);
  protected readonly mecanicos = signal<Mecanico[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly exito = signal<string | null>(null);
  protected readonly procesando = signal<number | null>(null);
  protected readonly fecha = formatoFechaHora;
  protected elegidos: Record<number, number | null> = {};

  protected readonly ingresadas = computed(() => (this.ordenes() ?? []).filter((o) => o.status === 'RECEIVED'));
  protected readonly enTaller = computed(() => (this.ordenes() ?? []).filter((o) => TECNICOS.includes(o.status)));
  protected readonly activos = computed(() => this.mecanicos().filter((m) => m.active).map((m) => ({
    ...m, carga: this.enTaller().filter((o) => o.mechanic_id === m.id).length,
  })));

  ngOnInit(): void {
    this.cargar();
  }

  private cargar(): void {
    forkJoin([this.http.get<Orden[]>('/api/ordenes'), this.http.get<Mecanico[]>('/api/usuarios/mecanicos')]).subscribe({
      next: ([o, m]) => {
        this.ordenes.set(o);
        this.mecanicos.set(m);
      },
      error: (e: unknown) => this.error.set(mensajeError(e, ERROR_INTERNO)),
    });
  }

  protected asignar(o: Orden): void {
    const mechanic_id = this.elegidos[o.id];
    if (!mechanic_id) return;
    this.procesando.set(o.id);
    this.error.set(null);
    this.exito.set(null);
    this.http.post<Orden>(`/api/ordenes/${o.id}/asignacion`, { mechanic_id: Number(mechanic_id), version: o.version })
      .subscribe({
        next: (r) => {
          this.procesando.set(null);
          this.exito.set(`${r.number} quedó asignada a ${r.mechanic_name}.`);
          this.elegidos[o.id] = null;
          this.cargar();
        },
        error: (e: unknown) => {
          this.procesando.set(null);
          this.error.set(mensajeError(e, ERROR_INTERNO));
        },
      });
  }
}
