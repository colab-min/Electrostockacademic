import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ICONOS, NombreIcono } from './iconos';

/**
 * Icono SVG del set Lucide (trazo 1,5 px). Decorativo por defecto (aria-hidden);
 * con `etiqueta` se anuncia a lectores de pantalla.
 */
@Component({
  selector: 'app-icono',
  templateUrl: './icono.html',
  styleUrl: './icono.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Icono {
  private readonly sanitizer = inject(DomSanitizer);
  readonly nombre = input.required<NombreIcono>();
  readonly tamano = input<20 | 24 | 16 | 32>(20);
  readonly etiqueta = input<string | null>(null);
  // Contenido constante del propio código (no viene del usuario), por eso es seguro confiar en él.
  protected readonly trazo = computed<SafeHtml>(() =>
    this.sanitizer.bypassSecurityTrustHtml(ICONOS[this.nombre()]));
}
