import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, inject, provideAppInitializer, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { routes } from './app.routes';
import { interceptorAuth } from './core/interceptor-auth';
import { SesionService } from './core/sesion.service';

/** Al recargar, intenta recuperar la sesión con la cookie de renovación. */
async function recuperarSesion(): Promise<void> {
  try {
    await firstValueFrom(inject(SesionService).renovar());
  } catch {
    /* sin sesión previa */
  }
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(withInterceptors([interceptorAuth])),
    provideAppInitializer(recuperarSesion),
  ],
};
