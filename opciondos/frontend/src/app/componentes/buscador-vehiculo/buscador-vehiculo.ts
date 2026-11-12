import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';
import { Icono } from '../icono/icono';

/**
 * Búsqueda por serie, placa o documento. Con `alEscribir`, busca sola 300 ms después
 * de la última tecla (desde 5 caracteres, el mínimo de una serie); Enter busca de inmediato.
 */
@Component({
  selector: 'app-buscador-vehiculo',
  imports: [Icono],
  templateUrl: './buscador-vehiculo.html',
  styleUrl: './buscador-vehiculo.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BuscadorVehiculo {
  readonly etiqueta = input('Serie, placa o documento');
  readonly buscando = input(false);
  readonly valorInicial = input('');
  readonly alEscribir = input(true);
  readonly buscar = output<string>();
  protected readonly texto = signal('');
  private espera: ReturnType<typeof setTimeout> | null = null;

  protected escribir(valor: string): void {
    this.texto.set(valor);
    if (!this.alEscribir()) return;
    if (this.espera) clearTimeout(this.espera);
    if (valor.trim().length >= 5) this.espera = setTimeout(() => this.enviar(), 300);
  }

  protected enviar(): void {
    if (this.espera) clearTimeout(this.espera);
    const q = (this.texto() || this.valorInicial()).trim();
    if (q) this.buscar.emit(q);
  }
}
