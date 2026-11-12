import { Injectable, signal } from '@angular/core';

export interface ToastItem {
  id: number;
  mensaje: string;
  tipo: 'exito' | 'info' | 'error';
}

/** Notificaciones breves de presentación: duran 4 s y se pueden cerrar. */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private siguiente = 1;
  readonly lista = signal<ToastItem[]>([]);

  mostrar(mensaje: string, tipo: ToastItem['tipo'] = 'exito'): void {
    const id = this.siguiente++;
    this.lista.update((l) => [...l, { id, mensaje, tipo }]);
    setTimeout(() => this.cerrar(id), 4000);
  }

  cerrar(id: number): void {
    this.lista.update((l) => l.filter((t) => t.id !== id));
  }
}
