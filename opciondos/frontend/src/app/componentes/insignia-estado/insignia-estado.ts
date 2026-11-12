import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

type Tipo = 'correcto' | 'informacion' | 'advertencia' | 'alerta' | 'neutra';

/** Insignias de estado de IS-4 7.6: cada una lleva texto, nunca solo color. */
const ESTADOS: Record<string, [string, Tipo]> = {
  HELD: ['En proceso', 'informacion'], CONFIRMED: ['Confirmada', 'correcto'], RESCHEDULED: ['Reprogramada', 'informacion'],
  CANCELLED: ['Cancelada', 'neutra'], NO_SHOW: ['No asistió', 'neutra'], ATTENDED: ['Atendida', 'neutra'],
  EXPIRED: ['Expirada', 'neutra'],
  RECEIVED: ['Ingresada', 'neutra'], ASSIGNED: ['Asignada', 'neutra'], DIAGNOSING: ['En diagnóstico', 'informacion'],
  WAITING_PARTS: ['Esperando repuesto', 'advertencia'], REPAIRING: ['En reparación', 'informacion'],
  FINISHED: ['Finalizada', 'correcto'], PENDING_PAYMENT: ['Pendiente de pago', 'advertencia'], PAID: ['Pagada', 'correcto'],
  DELIVERED: ['Entregada', 'correcto'], PENDING_INSTALLATION: ['Pendiente de instalación', 'advertencia'],
  HIGH: ['Prioridad alta', 'alerta'], MEDIUM: ['Prioridad media', 'advertencia'], LOW: ['Prioridad baja', 'neutra'],
  ACTIVE: ['Activo', 'correcto'], INACTIVE: ['Inactivo', 'alerta'], RESERVED: ['Reservado', 'advertencia'],
  INSTALLED: ['Instalado', 'correcto'], RETURNED: ['Retirado', 'neutra'], ALERT: ['En alerta', 'alerta'],
  BLOCKED: ['Bloqueado', 'alerta'], UNASSIGNED: ['Sin asignar', 'advertencia'],
  PENDING: ['Pendiente', 'advertencia'], SENT: ['Enviada', 'correcto'], UNDELIVERED: ['No entregada', 'alerta'],
};

/** Etiqueta en español de un código de estado (para gráficos y textos). */
export function etiquetaEstado(codigo: string): string {
  return ESTADOS[codigo]?.[0] ?? codigo;
}

@Component({
  selector: 'app-insignia-estado',
  templateUrl: './insignia-estado.html',
  styleUrl: './insignia-estado.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InsigniaEstado {
  /** Código del backend (CONFIRMED, REPAIRING, HIGH...) o un texto libre. */
  readonly estado = input.required<string>();
  /** Texto que reemplaza la etiqueta por defecto (p. ej. etiquetas públicas del seguimiento). */
  readonly texto = input<string | null>(null);
  protected readonly datos = computed(() => ESTADOS[this.estado()] ?? [this.estado(), 'neutra' as Tipo]);
}
