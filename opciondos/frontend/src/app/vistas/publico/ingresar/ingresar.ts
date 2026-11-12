import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { CabeceraVista } from '../../../componentes/cabecera-vista/cabecera-vista';
import { Campo } from '../../../componentes/campo/campo';
import { IlustracionVehiculo } from '../../../componentes/ilustracion-vehiculo/ilustracion-vehiculo';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { mensajeError } from '../../../core/errores';
import { INICIO_POR_ROL, RespuestaSesion, SesionService, Usuario } from '../../../core/sesion.service';

/** PU-01 Iniciar sesión (HU-21) con el paso obligatorio de contraseña temporal (HU-15, RN-52). */
@Component({
  selector: 'app-vista-ingresar',
  imports: [FormsModule, RouterLink, Aviso, Boton, CabeceraVista, Campo, IlustracionVehiculo, Tarjeta],
  templateUrl: './ingresar.html',
  styleUrl: './ingresar.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaIngresar {
  private readonly sesion = inject(SesionService);
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  protected readonly paso = signal<'login' | 'cambio'>('login');
  protected readonly procesando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected email = '';
  protected password = '';
  protected nueva = '';
  protected confirmacion = '';

  protected ingresar(): void {
    if (!this.email || !this.password) return;
    this.procesando.set(true);
    this.error.set(null);
    this.sesion.login(this.email, this.password).subscribe({
      next: (r) => {
        this.procesando.set(false);
        if (r.user.must_change_password) this.paso.set('cambio');
        else this.irAInicio(r.user);
      },
      error: (e: unknown) => {
        this.procesando.set(false);
        const estado = e instanceof HttpErrorResponse ? e.status : 0;
        this.error.set(estado === 401 || estado === 429
          ? mensajeError(e)
          : 'Servicio no disponible momentáneamente, intenta más tarde');
      },
    });
  }

  protected cambiar(): void {
    if (this.nueva !== this.confirmacion) {
      this.error.set('Las contraseñas no coinciden.');
      return;
    }
    this.procesando.set(true);
    this.error.set(null);
    this.http.post<RespuestaSesion>('/api/auth/change-password', { new_password: this.nueva, confirmation: this.confirmacion })
      .subscribe({
        next: (r) => {
          this.sesion.iniciar(r);
          this.irAInicio(r.user);
        },
        error: (e: unknown) => {
          this.procesando.set(false);
          this.error.set(mensajeError(e));
        },
      });
  }

  private irAInicio(usuario: Usuario): void {
    void this.router.navigateByUrl(INICIO_POR_ROL[usuario.role]);
  }
}
