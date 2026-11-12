import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { Campo } from '../../../componentes/campo/campo';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { camposConError, mensajeError } from '../../../core/errores';
import { INICIO_POR_ROL, RespuestaSesion, SesionService } from '../../../core/sesion.service';

/** PU-02 Crear cuenta (HU-21): solo cuentas Cliente, con autorización de datos (RN-51). */
@Component({
  selector: 'app-vista-crear-cuenta',
  imports: [FormsModule, RouterLink, Aviso, Boton, Campo, Tarjeta],
  templateUrl: './crear-cuenta.html',
  styleUrl: './crear-cuenta.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaCrearCuenta {
  private readonly http = inject(HttpClient);
  private readonly sesion = inject(SesionService);
  private readonly router = inject(Router);

  protected readonly procesando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly invalidos = signal<string[]>([]);
  protected readonly verAviso = signal(false);
  protected datos = { full_name: '', document_type: 'CC', document_number: '', phone: '', email: '', password: '', data_consent: false };

  protected crear(): void {
    if (!this.datos.data_consent) {
      this.error.set('Debes autorizar el tratamiento de tus datos para crear la cuenta');
      this.invalidos.set(['data_consent']);
      return;
    }
    this.procesando.set(true);
    this.error.set(null);
    this.invalidos.set([]);
    this.http.post<RespuestaSesion>('/api/auth/register', this.datos).subscribe({
      next: (r) => {
        this.sesion.iniciar(r);
        void this.router.navigateByUrl(INICIO_POR_ROL[r.user.role]);
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        this.error.set(mensajeError(e));
        this.invalidos.set(camposConError(e));
      },
    });
  }

  protected invalido(campo: string): boolean {
    return this.invalidos().includes(campo);
  }
}
