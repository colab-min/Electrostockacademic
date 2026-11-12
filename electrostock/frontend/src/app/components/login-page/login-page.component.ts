import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { I18nService, TranslationKey } from '../../core/i18n.service';
import { SessionService } from '../../core/session.service';

@Component({
  imports: [FormsModule, RouterLink],
  standalone: true,
  styleUrl: './login-page.component.css',
  templateUrl: './login-page.component.html',
})
export class LoginPageComponent {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);
  readonly loading = signal(false);
  readonly error = signal('');
  email = '';
  password = '';

  t(key: TranslationKey): string {
    return this.i18n.translate(key);
  }

  submit(): void {
    this.error.set('');
    this.loading.set(true);
    this.session.login(this.email, this.password).subscribe({
      next: (result) => {
        this.loading.set(false);
        if (result.must_change_password) this.session.mustChangePassword.set(true);
        const destination = result.must_change_password
          ? '/perfil/cambiar-contrasena'
          : result.user.role === 'CUSTOMER'
            ? '/cliente/citas'
            : result.user.role === 'RECEPTIONIST'
              ? '/recepcion/agenda'
              : result.user.role === 'MECHANIC'
                ? '/taller/bahia'
                : '/admin/indicadores';
        void this.router.navigateByUrl(destination);
      },
      error: () => {
        this.loading.set(false);
        this.error.set(this.t('loginError'));
      },
    });
  }
}
