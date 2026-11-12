import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';

import { SessionService } from './session.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith('/api/v1/')) {
    return next(request);
  }
  if (request.url.endsWith('/auth/refresh')) {
    return next(request.clone({ withCredentials: true }));
  }

  const session = inject(SessionService);
  const router = inject(Router);
  const token = session.accessToken();
  const authRequest = request.clone({
    setHeaders: token ? { Authorization: 'Bearer ' + token } : {},
    withCredentials: true,
  });

  return next(authRequest).pipe(
    catchError((error: unknown) => {
      const isAuthRequest = ['/auth/login', '/auth/register', '/auth/logout'].some((path) =>
        request.url.endsWith(path),
      );
      if (!(error instanceof HttpErrorResponse) || error.status !== 401 || isAuthRequest) {
        return throwError(() => error);
      }

      return session.refreshAccessToken().pipe(
        switchMap((freshToken) =>
          next(
            request.clone({
              setHeaders: { Authorization: 'Bearer ' + freshToken },
              withCredentials: true,
            }),
          ),
        ),
        catchError((refreshError: unknown) => {
          session.logout();
          void router.navigateByUrl('/ingresar');
          return throwError(() => refreshError);
        }),
      );
    }),
  );
};
