import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

export type EstadoDia = 'disponible' | 'sin-cupo' | 'bloqueado' | 'cerrado';

/** Calendario mensual de selección de día (CL-03, CL-06, SE-01). Fechas en formato AAAA-MM-DD. */
@Component({
  selector: 'app-calendario-mes',
  templateUrl: './calendario-mes.html',
  styleUrl: './calendario-mes.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CalendarioMes {
  /** Primer día del mes que se muestra, AAAA-MM-01. */
  readonly mes = input.required<string>();
  readonly dias = input<Record<string, EstadoDia>>({});
  readonly seleccionado = input<string | null>(null);
  readonly elegir = output<string>();
  readonly cambiarMes = output<string>();
  protected readonly semana = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

  protected readonly titulo = computed(() =>
    new Intl.DateTimeFormat('es-CO', { month: 'long', year: 'numeric' }).format(new Date(`${this.mes()}T12:00:00`)));

  protected readonly celdas = computed(() => {
    const [y, m] = this.mes().split('-').map(Number);
    const primero = new Date(y, m - 1, 1);
    const vacias = (primero.getDay() + 6) % 7;
    const total = new Date(y, m, 0).getDate();
    const celdas: ({ fecha: string; dia: number; estado: EstadoDia } | null)[] = Array(vacias).fill(null);
    for (let d = 1; d <= total; d++) {
      const fecha = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      celdas.push({ fecha, dia: d, estado: this.dias()[fecha] ?? 'cerrado' });
    }
    return celdas;
  });

  protected mover(delta: number): void {
    const [y, m] = this.mes().split('-').map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    this.cambiarMes.emit(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`);
  }
}
