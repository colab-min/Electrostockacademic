import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { EspacioFotos } from '../../../componentes/espacio-fotos/espacio-fotos';
import {
  DatosVehiculo, FormularioVehiculo, cuerpoVehiculo, erroresDeCampos, vehiculoVacio,
} from '../../../componentes/formulario-vehiculo/formulario-vehiculo';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { camposConError, mensajeError } from '../../../core/errores';

/** CL-07 Registrar vehículo (HU-22): mismo formulario que SE-03, sin casilla (la autorización se dio en PU-02). */
@Component({
  selector: 'app-vista-registrar-vehiculo',
  imports: [FormsModule, RouterLink, Aviso, Boton, EspacioFotos, FormularioVehiculo, Tarjeta],
  templateUrl: './registrar-vehiculo.html',
  styleUrl: './registrar-vehiculo.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaRegistrarVehiculo {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  protected readonly vehiculo = signal<DatosVehiculo>(vehiculoVacio());
  protected readonly errores = signal<Record<string, string>>({});
  protected readonly error = signal<string | null>(null);
  protected readonly procesando = signal(false);

  protected registrar(): void {
    this.procesando.set(true);
    this.error.set(null);
    this.errores.set({});
    this.http.post('/api/clientes/vehiculos', cuerpoVehiculo(this.vehiculo())).subscribe({
      next: () => void this.router.navigateByUrl('/cliente/citas'),
      error: (e: unknown) => {
        this.procesando.set(false);
        const campos = camposConError(e);
        const detalle = mensajeError(e);
        if (campos.length) {
          this.error.set('Por favor completa todos los campos obligatorios con un formato válido');
          this.errores.set(erroresDeCampos(campos));
        } else if (e instanceof HttpErrorResponse && e.status === 409) {
          this.error.set(detalle);
          this.errores.set({ [detalle.includes('placa') ? 'plate' : 'serial_number']: detalle });
        } else this.error.set(detalle);
      },
    });
  }
}
