import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { LoginPageComponent } from './login-page.component';

describe('LoginPageComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoginPageComponent],
      providers: [provideHttpClient(), provideRouter([])],
    }).compileComponents();
  });

  it('associates labels with sign-in fields', () => {
    const fixture = TestBed.createComponent(LoginPageComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('label[for="email"]')).toBeTruthy();
    expect(element.querySelector('#email')?.getAttribute('autocomplete')).toBe('username');
    expect(element.querySelector('label[for="password"]')).toBeTruthy();
  });
});
