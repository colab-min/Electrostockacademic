import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnInit, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { Campo } from '../../../componentes/campo/campo';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';

interface Encuesta {
  number: string;
  answered: boolean;
}

/** CL-09 Encuesta de satisfacción (HU-16): pública, con token de un solo uso. */
@Component({
  selector: 'app-vista-encuesta',
  imports: [FormsModule, Aviso, Boton, Campo, Tarjeta],
  templateUrl: './encuesta.html',
  styleUrl: './encuesta.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaEncuesta implements OnInit {
  readonly token = input.required<string>();
  private readonly http = inject(HttpClient);

  protected readonly encuesta = signal<Encuesta | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly procesando = signal(false);
  protected readonly puntajes = [1, 2, 3, 4, 5];
  protected puntaje: number | null = null;
  protected comentario = '';

  ngOnInit(): void {
    this.http.get<Encuesta>(`/api/encuestas/${encodeURIComponent(this.token())}`).subscribe({
      next: (e) => this.encuesta.set(e),
      error: (e: unknown) => this.error.set(mensajeError(e)),
    });
  }

  protected enviar(): void {
    if (!this.puntaje) return;
    this.procesando.set(true);
    this.error.set(null);
    this.http.post<Encuesta>(`/api/encuestas/${encodeURIComponent(this.token())}`,
      { score: this.puntaje, comment: this.comentario || null }).subscribe({
      next: (e) => {
        this.procesando.set(false);
        this.encuesta.set(e);
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        this.error.set(mensajeError(e));
      },
    });
  }
}
