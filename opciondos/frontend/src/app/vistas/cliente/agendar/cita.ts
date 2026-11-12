import { formatoFecha } from '../../../core/formato';

/** Cita tal como la devuelve /api/agenda (compartida por CL-01, CL-02 a CL-05 y CL-06). */
export interface Cita {
  id: number;
  code: string;
  status: string;
  starts_at: string;
  hold_expires_at: string | null;
  limite_cambio: string;
  puede_cambiar: boolean;
  service: { id: number; name: string; duration_min: number; labor_price: number };
  vehicle: { id: number; serial_number: string; plate: string | null; brand: string; model: string };
  repuestos: { name: string; quantity: number }[];
}

export interface Franja {
  id: number;
  hora: string;
  estado: 'libre' | 'sin-cupo' | 'bloqueado';
  ocupados: number;
  capacidad: number;
}

const hora = new Intl.DateTimeFormat('es-CO', { timeStyle: 'short' });

export const textoHora = (iso: string): string => hora.format(new Date(iso));

/** IS-4 8: "Puedes cancelar o reprogramar hasta las {hora} del {fecha}." */
export const textoLimite = (c: Cita): string =>
  `Puedes cancelar o reprogramar hasta las ${textoHora(c.limite_cambio)} del ${formatoFecha(c.limite_cambio.slice(0, 10))}.`;

export const FUERA_VENTANA =
  'Ya no es posible cancelar: falta menos de 1 hora para tu cita. Si no asistes, la cita se libera sola 15 minutos después de su hora.';
