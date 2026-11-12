import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { SessionService } from './session.service';

export const authGuard: CanActivateFn = (route) => {
  const session = inject(SessionService);
  const router = inject(Router);
  const user = session.user();
  const roles = route.data['roles'] as string[] | undefined;
  if (!user || (roles && !roles.includes(user.role))) {
    return router.createUrlTree(['/ingresar']);
  }
  if (
    session.mustChangePassword()
    && route.routeConfig?.path !== 'perfil/cambiar-contrasena'
  ) {
    return router.createUrlTree(['/perfil/cambiar-contrasena']);
  }
  return true;
};
