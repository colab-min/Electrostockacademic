import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { SesionService } from './sesion.service';

const SIN_RENOVACION = /\/api\/auth\/(login|refresh|logout|register)$/;

function conToken(req: HttpRequest<unknown>, token: string): HttpRequest<unknown> {
  return req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
}

/** Agrega el Bearer; ante un 401 renueva una vez y reintenta; si no puede, vuelve al login. */
export const interceptorAuth: HttpInterceptorFn = (req, next) => {
  const sesion = inject(SesionService);
  const router = inject(Router);
  const token = sesion.token();
  return next(token ? conToken(req, token) : req).pipe(
    catchError((err: unknown) => {
      if (!(err instanceof HttpErrorResponse) || err.status !== 401 || !token || SIN_RENOVACION.test(req.url)) {
        return throwError(() => err);
      }
      return sesion.renovar().pipe(
        switchMap((nuevo) => next(conToken(req, nuevo))),
        catchError(() => {
          sesion.limpiar();
          void router.navigate(['/ingresar'], { queryParams: { aviso: 'sesion_expirada' } });
          return throwError(() => err);
        }),
      );
    }),
  );
};
