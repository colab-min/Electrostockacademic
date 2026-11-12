import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import { Aviso } from './componentes/aviso/aviso';
import { BarraSuperior } from './componentes/barra-superior/barra-superior';
import { Toast } from './componentes/toast/toast';

const AVISOS: Record<string, { texto: string; tipo: 'advertencia' | 'informacion' }> = {
  sin_permiso: { texto: 'No tiene permisos para esta sección', tipo: 'advertencia' },
  sesion_expirada: { texto: 'Tu sesión ha expirado. Inicia sesión de nuevo para guardar los cambios.', tipo: 'informacion' },
};

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, BarraSuperior, Aviso, Toast],
  templateUrl: './app.html',
  styleUrl: './app.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  private readonly router = inject(Router);
  private readonly url = toSignal(
    this.router.events.pipe(filter((e) => e instanceof NavigationEnd), map(() => this.router.url)),
    { initialValue: '' },
  );
  /** Aviso que llega por la URL tras una redirección (sin permiso o sesión expirada). */
  protected readonly aviso = computed(() => AVISOS[this.router.parseUrl(this.url()).queryParams['aviso'] as string] ?? null);
}
