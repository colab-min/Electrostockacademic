import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, effect, inject, input, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { Subscription, switchMap, timer } from 'rxjs';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { Campo } from '../../../componentes/campo/campo';
import { InsigniaEstado } from '../../../componentes/insignia-estado/insignia-estado';
import { EventoLinea, LineaTiempo } from '../../../componentes/linea-tiempo/linea-tiempo';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { formatoFechaHora } from '../../../core/formato';

interface Seguimiento {
  tipo: string;
  modelo: string;
  estado: string;
  estado_publico: string;
  linea_tiempo: EventoLinea[];
  entrega_estimada: string | null;
}

const FORMATO = /^[A-HJ-NP-Z2-9]{10}$/;
const NO_ENCONTRADO = 'No encontramos información con ese código. Verifica e intenta de nuevo.';

/** PU-03 Seguimiento público (HU-07): se refresca cada 3 s para ver en vivo el cambio del mecánico. */
@Component({
  selector: 'app-vista-seguimiento',
  imports: [FormsModule, Aviso, Boton, Campo, InsigniaEstado, LineaTiempo, Tarjeta],
  templateUrl: './seguimiento.html',
  styleUrl: './seguimiento.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaSeguimiento {
  readonly codigo = input<string>();
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private sondeo: Subscription | null = null;

  protected texto = '';
  protected readonly datos = signal<Seguimiento | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly cargando = signal(false);
  protected readonly fecha = formatoFechaHora;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.sondeo?.unsubscribe());
    effect(() => {
      const c = this.codigo();
      if (c) untracked(() => {
        this.texto = c;
        this.consultar(c.toUpperCase());
      });
    });
  }

  protected buscar(): void {
    const c = this.texto.trim().toUpperCase();
    if (c === this.codigo()) this.consultar(c);
    else void this.router.navigate(['/seguimiento', c]);
  }

  private consultar(codigo: string): void {
    this.sondeo?.unsubscribe();
    this.datos.set(null);
    this.error.set(null);
    if (!FORMATO.test(codigo)) {
      this.error.set(NO_ENCONTRADO); // un formato inválido ni siquiera se busca
      return;
    }
    this.cargando.set(true);
    this.sondeo = timer(0, 3000)
      .pipe(switchMap(() => this.http.get<Seguimiento>(`/api/seguimiento/${codigo}`)))
      .subscribe({
        next: (d) => {
          this.cargando.set(false);
          this.datos.set(d);
        },
        error: (e: unknown) => {
          this.cargando.set(false);
          const estado = e instanceof HttpErrorResponse ? e.status : 0;
          this.error.set(estado === 404 ? NO_ENCONTRADO : mensajeError(e));
        },
      });
  }
}
