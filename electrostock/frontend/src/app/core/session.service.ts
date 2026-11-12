import { HttpClient } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { finalize, map, Observable, shareReplay, tap } from 'rxjs';

import { LoginResponse, SessionUser } from './models';

@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly http = inject(HttpClient);
  readonly accessToken = signal<string | null>(null);
  readonly user = signal<SessionUser | null>(this.restoreUser());
  readonly mustChangePassword = signal(this.user()?.must_change_password ?? false);
  private refreshInFlight: Observable<string> | null = null;

  constructor() {
    localStorage.removeItem('electrostock.accessToken');
  }

  login(email: string, password: string) {
    return this.http
      .post<LoginResponse>('/api/v1/auth/login', { email, password })
      .pipe(
        tap((result) => {
          this.accessToken.set(result.access_token);
          localStorage.setItem('electrostock.user', JSON.stringify(result.user));
          this.user.set(result.user);
          this.mustChangePassword.set(result.must_change_password);
        }),
      );
  }

  register(payload: {
    full_name: string;
    email: string;
    password: string;
    document_type: string;
    document_number: string;
    phone: string;
    data_consent: boolean;
  }) {
    return this.http
      .post<LoginResponse>('/api/v1/auth/register', payload)
      .pipe(
        tap((result) => {
          this.accessToken.set(result.access_token);
          localStorage.setItem('electrostock.user', JSON.stringify(result.user));
          this.user.set(result.user);
        }),
      );
  }

  refreshAccessToken(): Observable<string> {
    if (!this.refreshInFlight) {
      this.refreshInFlight = this.http
        .post<{ access_token: string }>('/api/v1/auth/refresh', {}, { withCredentials: true })
        .pipe(
          map((result) => result.access_token),
          tap((token) => this.accessToken.set(token)),
          finalize(() => {
            this.refreshInFlight = null;
          }),
          shareReplay({ bufferSize: 1, refCount: false }),
        );
    }
    return this.refreshInFlight;
  }

  completePasswordChange(): void {
    this.mustChangePassword.set(false);
    const user = this.user();
    if (!user) {
      return;
    }
    const updatedUser = { ...user, must_change_password: false };
    this.user.set(updatedUser);
    localStorage.setItem('electrostock.user', JSON.stringify(updatedUser));
  }

  logout(): void {
    this.accessToken.set(null);
    localStorage.removeItem('electrostock.accessToken');
    localStorage.removeItem('electrostock.user');
    this.user.set(null);
    this.mustChangePassword.set(false);
  }

  private restoreUser(): SessionUser | null {
    const stored = localStorage.getItem('electrostock.user');
    if (!stored) {
      return null;
    }
    try {
      return JSON.parse(stored) as SessionUser;
    } catch {
      localStorage.removeItem('electrostock.user');
      localStorage.removeItem('electrostock.accessToken');
      return null;
    }
  }
}
