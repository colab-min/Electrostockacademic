import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Icono } from '../icono/icono';
import { ToastService } from './toast.service';

/** Contenedor de notificaciones breves, abajo a la derecha (una sola instancia, en el shell). */
@Component({
  selector: 'app-toast',
  imports: [Icono],
  templateUrl: './toast.html',
  styleUrl: './toast.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Toast {
  protected readonly toasts = inject(ToastService);
}
