import { inject } from '@angular/core';
import { CanMatchFn, Router } from '@angular/router';
import { INICIO_POR_ROL, Rol, SesionService } from './sesion.service';

/** Guardia por rol: solo mejora la experiencia; el backend valida el rol en cada ruta. */
export function guardiaRol(...permitidos: Rol[]): CanMatchFn {
  return () => {
    const sesion = inject(SesionService);
    const router = inject(Router);
    const rol = sesion.rol();
    if (rol === null) return router.createUrlTree(['/ingresar']);
    if (permitidos.includes(rol)) return true;
    return router.createUrlTree([INICIO_POR_ROL[rol]], { queryParams: { aviso: 'sin_permiso' } });
  };
}
