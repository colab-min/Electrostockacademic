import { ChangeDetectionStrategy, Component, ElementRef, effect, input, output, viewChild } from '@angular/core';
import { Boton } from '../boton/boton';

/**
 * Diálogo modal (elevación 3). El foco entra al diálogo, vuelve al botón que lo abrió al cerrar
 * y Esc equivale a "Volver".
 */
@Component({
  selector: 'app-dialogo-confirmacion',
  imports: [Boton],
  templateUrl: './dialogo-confirmacion.html',
  styleUrl: './dialogo-confirmacion.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DialogoConfirmacion {
  readonly abierto = input(false);
  readonly titulo = input.required<string>();
  readonly mensaje = input<string | null>(null);
  readonly textoConfirmar = input('Confirmar');
  readonly textoCancelar = input('Volver');
  readonly variante = input<'peligro' | 'primario'>('peligro');
  readonly procesando = input(false);
  readonly confirmar = output<void>();
  readonly cancelar = output<void>();
  private readonly dialogo = viewChild<ElementRef<HTMLDialogElement>>('dialogo');
  private origen: HTMLElement | null = null;

  constructor() {
    effect(() => {
      const d = this.dialogo()?.nativeElement;
      if (!d) return;
      if (this.abierto() && !d.open) {
        this.origen = document.activeElement as HTMLElement | null;
        d.showModal?.();
      }
      if (!this.abierto() && d.open) {
        d.close();
        this.origen?.focus();
      }
    });
  }
}
