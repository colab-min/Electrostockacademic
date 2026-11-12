import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';

/** Búsqueda por serie, placa o documento (SE-02, SE-04, ME-03). */
@Component({
  selector: 'app-buscador-vehiculo',
  templateUrl: './buscador-vehiculo.html',
  styleUrl: './buscador-vehiculo.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BuscadorVehiculo {
  readonly etiqueta = input('Serie, placa o documento');
  readonly buscando = input(false);
  readonly valorInicial = input('');
  readonly buscar = output<string>();
  protected readonly texto = signal('');

  protected enviar(): void {
    const q = (this.texto() || this.valorInicial()).trim();
    if (q) this.buscar.emit(q);
  }
}
