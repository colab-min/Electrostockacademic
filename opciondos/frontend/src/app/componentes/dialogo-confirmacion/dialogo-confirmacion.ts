import { ChangeDetectionStrategy, Component, ElementRef, effect, input, output, viewChild } from '@angular/core';
import { Boton } from '../boton/boton';

/** Diálogo para acciones destructivas: nombra el objeto y sus efectos; Esc equivale a "Volver". */
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
  readonly procesando = input(false);
  readonly confirmar = output<void>();
  readonly cancelar = output<void>();
  private readonly dialogo = viewChild<ElementRef<HTMLDialogElement>>('dialogo');

  constructor() {
    effect(() => {
      const d = this.dialogo()?.nativeElement;
      if (!d) return;
      if (this.abierto() && !d.open) d.showModal?.();
      if (!this.abierto() && d.open) d.close();
    });
  }
}
