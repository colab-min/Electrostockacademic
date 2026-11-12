import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Aviso } from '../../../componentes/aviso/aviso';
import { Boton } from '../../../componentes/boton/boton';
import { Campo } from '../../../componentes/campo/campo';
import { EspacioFotos } from '../../../componentes/espacio-fotos/espacio-fotos';
import {
  DatosVehiculo, FormularioVehiculo, TIPOS_VEHICULO, cuerpoVehiculo, erroresDeCampos, vehiculoVacio,
} from '../../../componentes/formulario-vehiculo/formulario-vehiculo';
import { Tarjeta } from '../../../componentes/tarjeta/tarjeta';
import { camposConError, mensajeError } from '../../../core/errores';

interface Cliente {
  id: number;
  document_type: string;
  document_number: string;
  full_name: string;
  phone: string;
  email: string | null;
  has_account: boolean;
  vehicles: { id: number; type: string; serial_number: string; plate: string | null; brand: string; model: string }[];
}

const FORMATO = 'Por favor complete todos los campos obligatorios con un formato válido';
const AUTORIZACION = 'Debe registrar la autorización del cliente para continuar';
const ERROR_SERVIDOR = 'No fue posible completar la acción. Intente de nuevo en unos segundos.';
const TEXTOS_CLIENTE: Record<string, string> = {
  document_number: 'CC: 6 a 10 dígitos. CE y PA: 6 a 12 letras o números.',
  full_name: 'Campo obligatorio.', phone: 'Entre 7 y 20 dígitos.', email: 'Correo con formato válido.',
};

/** SE-03 Registrar cliente y vehículo, con edición de contacto de un cliente existente (HU-22, RN-47, RN-51). */
@Component({
  selector: 'app-vista-registrar-cliente',
  imports: [FormsModule, Aviso, Boton, Campo, EspacioFotos, FormularioVehiculo, Tarjeta],
  templateUrl: './registrar-cliente.html',
  styleUrl: './registrar-cliente.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VistaRegistrarCliente {
  private readonly http = inject(HttpClient);
  protected readonly tipos = TIPOS_VEHICULO;

  protected readonly modo = signal<'buscar' | 'existente' | 'nuevo'>('buscar');
  protected readonly cliente = signal<Cliente | null>(null);
  protected readonly vehiculo = signal<DatosVehiculo>(vehiculoVacio());
  protected readonly errores = signal<Record<string, string>>({});
  protected readonly error = signal<string | null>(null);
  protected readonly exito = signal<string | null>(null);
  protected readonly buscando = signal(false);
  protected readonly guardando = signal(false);
  protected readonly guardandoContacto = signal(false);
  protected readonly verAviso = signal(false);

  protected documento = { document_type: 'CC', document_number: '' };
  protected contacto = { phone: '', email: '' };
  protected nuevo = { full_name: '', phone: '', email: '', data_consent: false };

  protected buscar(mensaje: string | null = null): void {
    if (!this.documento.document_number.trim()) return;
    this.buscando.set(true);
    this.limpiarMensajes();
    this.exito.set(mensaje);
    this.http.get<Cliente>('/api/clientes', { params: this.documento }).subscribe({
      next: (c) => {
        this.buscando.set(false);
        this.cliente.set(c);
        this.contacto = { phone: c.phone, email: c.email ?? '' };
        this.vehiculo.set(vehiculoVacio());
        this.modo.set('existente');
        if (mensaje) window.scrollTo({ top: 0 });
      },
      error: (e: unknown) => {
        this.buscando.set(false);
        if (e instanceof HttpErrorResponse && e.status === 404) {
          this.cliente.set(null);
          this.nuevo = { full_name: '', phone: '', email: '', data_consent: false };
          this.modo.set('nuevo');
        } else this.error.set(mensajeError(e, ERROR_SERVIDOR));
      },
    });
  }

  protected otraBusqueda(): void {
    this.limpiarMensajes();
    this.modo.set('buscar');
    this.cliente.set(null);
    this.documento = { document_type: this.documento.document_type, document_number: '' };
  }

  protected registrar(): void {
    this.limpiarMensajes();
    const vehicle = cuerpoVehiculo(this.vehiculo());
    const c = this.cliente();
    if (!c && !this.nuevo.data_consent) {
      this.error.set(AUTORIZACION);
      this.errores.set({ data_consent: AUTORIZACION });
      return;
    }
    const peticion = c
      ? this.http.post('/api/clientes/vehiculos', { ...vehicle, customer_id: c.id })
      : this.http.post('/api/clientes', { ...this.documento, ...this.nuevo, vehicle });
    this.guardando.set(true);
    peticion.subscribe({
      next: () => {
        this.guardando.set(false);
        this.buscar(c ? 'Vehículo registrado correctamente' : 'Cliente y vehículo registrados correctamente');
      },
      error: (e: unknown) => {
        this.guardando.set(false);
        this.mostrarError(e);
      },
    });
  }

  protected guardarContacto(): void {
    const c = this.cliente();
    if (!c) return;
    this.limpiarMensajes();
    this.guardandoContacto.set(true);
    this.http.patch<Cliente>(`/api/clientes/${c.id}`, { phone: this.contacto.phone, email: this.contacto.email || null })
      .subscribe({
        next: (actualizado) => {
          this.guardandoContacto.set(false);
          this.cliente.set(actualizado);
          this.exito.set('Datos de contacto actualizados.');
        },
        error: (e: unknown) => {
          this.guardandoContacto.set(false);
          this.mostrarError(e);
        },
      });
  }

  protected campoError(campo: string): string | null {
    return this.errores()[campo] ?? null;
  }

  private mostrarError(e: unknown): void {
    const campos = camposConError(e);
    const detalle = mensajeError(e, ERROR_SERVIDOR);
    if (campos.length) {
      this.error.set(FORMATO);
      this.errores.set(erroresDeCampos(campos, TEXTOS_CLIENTE));
    } else if (e instanceof HttpErrorResponse && e.status === 409) {
      this.error.set(detalle);
      const campo = detalle.includes('serie') ? 'serial_number' : detalle.includes('placa') ? 'plate' : 'document_number';
      this.errores.set({ [campo]: detalle });
    } else this.error.set(detalle);
  }

  private limpiarMensajes(): void {
    this.error.set(null);
    this.exito.set(null);
    this.errores.set({});
  }
}
