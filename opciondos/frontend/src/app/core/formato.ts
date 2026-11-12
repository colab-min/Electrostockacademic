/** Formatos colombianos (es-CO) usados por varias vistas. */
const pesos = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });
const fechaHora = new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium', timeStyle: 'short' });
const fecha = new Intl.DateTimeFormat('es-CO', { dateStyle: 'long' });

export const formatoPesos = (valor: number): string => pesos.format(valor);
export const formatoFechaHora = (iso: string): string => fechaHora.format(new Date(iso));
export const formatoFecha = (iso: string): string =>
  fecha.format(new Date(iso.length === 10 ? `${iso}T12:00:00` : iso));
