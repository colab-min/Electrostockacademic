import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, finalize, map, shareReplay, tap } from 'rxjs';

export type Rol = 'CUSTOMER' | 'RECEPTIONIST' | 'MECHANIC' | 'ADMIN';

export interface Usuario {
  id: number;
  full_name: string;
  email: string;
  role: Rol;
  must_change_password: boolean;
}

export interface RespuestaSesion {
  access_token: string;
  user: Usuario;
}

/** Vista principal de cada rol tras iniciar sesión. */
export const INICIO_POR_ROL: Record<Rol, string> = {
  CUSTOMER: '/cliente/citas',
  RECEPTIONIST: '/recepcion/agenda',
  MECHANIC: '/taller/bahia',
  ADMIN: '/admin/indicadores',
};

/** Sesión: el JWT de acceso vive solo en memoria; la renovación va en una cookie HttpOnly. */
@Injectable({ providedIn: 'root' })
export class SesionService {
  private readonly http = inject(HttpClient);
  private readonly tokenSignal = signal<string | null>(null);
  private readonly usuarioSignal = signal<Usuario | null>(null);
  private renovando$: Observable<string> | null = null;

  readonly token = this.tokenSignal.asReadonly();
  readonly usuario = this.usuarioSignal.asReadonly();
  readonly rol = computed(() => this.usuarioSignal()?.role ?? null);

  iniciar(r: RespuestaSesion): void {
    this.tokenSignal.set(r.access_token);
    this.usuarioSignal.set(r.user);
  }

  limpiar(): void {
    this.tokenSignal.set(null);
    this.usuarioSignal.set(null);
  }

  login(email: string, password: string): Observable<RespuestaSesion> {
    return this.http.post<RespuestaSesion>('/api/auth/login', { email, password }).pipe(tap((r) => this.iniciar(r)));
  }

  /** Una sola renovación en curso; las peticiones concurrentes esperan la misma. */
  renovar(): Observable<string> {
    this.renovando$ ??= this.http.post<RespuestaSesion>('/api/auth/refresh', null).pipe(
      tap((r) => this.iniciar(r)),
      map((r) => r.access_token),
      finalize(() => (this.renovando$ = null)),
      shareReplay(1),
    );
    return this.renovando$;
  }

  salir(): Observable<void> {
    return this.http.post<void>('/api/auth/logout', null).pipe(finalize(() => this.limpiar()));
  }
}
