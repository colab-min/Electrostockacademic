import { HttpErrorResponse } from '@angular/common/http';

const GENERICO = 'No fue posible completar la acción. Intenta de nuevo en unos segundos.';

/** Mensaje para mostrar a partir de un error HTTP del backend (campo `detail`). */
export function mensajeError(err: unknown, porDefecto = GENERICO): string {
  if (err instanceof HttpErrorResponse) {
    if (err.status === 0 || err.status >= 500) return porDefecto;
    const detail = (err.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') return detail;
  }
  return porDefecto;
}

/** Campos marcados por el backend en un 422 de validación. */
export function camposConError(err: unknown): string[] {
  return err instanceof HttpErrorResponse ? ((err.error as { fields?: string[] } | null)?.fields ?? []) : [];
}
