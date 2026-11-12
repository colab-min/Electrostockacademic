import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { RegisterPageComponent } from './register-page.component';

describe('RegisterPageComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RegisterPageComponent],
      providers: [provideHttpClient(), provideRouter([])],
    }).compileComponents();
  });

  it('requires an explicit consent checkbox', () => {
    const fixture = TestBed.createComponent(RegisterPageComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('input[type="checkbox"][required]')).toBeTruthy();
    expect(element.querySelector('label[for="consent"]')).toBeTruthy();
  });
});
