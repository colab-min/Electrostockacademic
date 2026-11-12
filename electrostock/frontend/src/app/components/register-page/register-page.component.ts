import { Component, inject, signal } from '@angular/core';
import { FormsModule, NgForm } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { I18nService, TranslationKey } from '../../core/i18n.service';
import { SessionService } from '../../core/session.service';

@Component({
  imports: [FormsModule, RouterLink],
  standalone: true,
  styleUrl: './register-page.component.css',
  templateUrl: './register-page.component.html',
})
export class RegisterPageComponent {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);
  readonly loading = signal(false);
  readonly error = signal('');
  fullName = '';
  email = '';
  password = '';
  documentType = 'CC';
  documentNumber = '';
  phone = '';
  dataConsent = false;

  t(key: TranslationKey): string {
    return this.i18n.translate(key);
  }

  submit(form: NgForm): void {
    this.error.set('');
    if (
      form.invalid || !this.fullName.trim() || !this.documentNumber.trim() ||
      !this.phone.trim() || !this.dataConsent
    ) {
      this.error.set(this.t('required'));
      return;
    }
    this.loading.set(true);
    this.session.register({
      full_name: this.fullName.trim(),
      email: this.email.trim(),
      password: this.password,
      document_type: this.documentType,
      document_number: this.documentNumber.trim(),
      phone: this.phone.trim(),
      data_consent: this.dataConsent,
    }).subscribe({
      next: () => {
        this.loading.set(false);
        void this.router.navigateByUrl('/cliente/citas');
      },
      error: (error: { error?: { detail?: string } }) => {
        this.loading.set(false);
        this.error.set(error.error?.detail ?? this.t('registrationError'));
      },
    });
  }
}
