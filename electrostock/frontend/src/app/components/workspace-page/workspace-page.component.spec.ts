import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { I18nService } from '../../core/i18n.service';
import { WorkspacePageComponent } from './workspace-page.component';

describe('WorkspacePageComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspacePageComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
  });

  it('localizes no-show appointment status in both supported languages', () => {
    const fixture = TestBed.createComponent(WorkspacePageComponent);
    const i18n = TestBed.inject(I18nService);

    expect(fixture.componentInstance.displayStatus('NO_SHOW')).toBe('No asistió');

    i18n.locale.set('en');
    expect(fixture.componentInstance.displayStatus('NO_SHOW')).toBe('Did not attend');
  });

  it('renders a named page heading and a refresh action', () => {
    const fixture = TestBed.createComponent(WorkspacePageComponent);
    fixture.detectChanges();
    const requests = TestBed.inject(HttpTestingController);
    requests.expectOne('/api/v1/work-orders').flush([
      { id: 'work-order-1', number: 'OT-1', status: 'WAITING_PARTS', description: 'Motor' },
      { id: 'work-order-2', active: true },
    ]);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('h1')?.textContent).toContain('Resumen del taller');
    expect(element.querySelector('button')?.textContent).toContain('Actualizar');
    expect(element.querySelector('.table-wrap')?.getAttribute('tabindex')).toBe('0');
    expect(element.querySelector('tbody')?.textContent).toContain('OT-1');
    expect(element.querySelector('tbody')?.textContent).toContain('Esperando repuesto');
    expect(element.querySelector('tbody')?.textContent).toContain('Activo');
    expect(element.querySelector('tbody')?.textContent).not.toContain('#2');
    requests.verify();
  });

  it('shows updated catalog data after saving and reloading from the API', () => {
    const fixture = TestBed.createComponent(WorkspacePageComponent);
    fixture.detectChanges();
    const requests = TestBed.inject(HttpTestingController);
    requests.expectOne('/api/v1/work-orders').flush([]);

    const component = fixture.componentInstance;
    component.page.set('catalog');
    component.managementRecords.set([
      { id: 'service-1', code: 'DIAG-1', name: 'Diagnóstico', price: 10000, duration_minutes: 30, active: true },
    ]);
    component.editRecord('service-1');
    component.editForm.name = 'Diagnóstico actualizado';
    component.saveRecord();

    requests.expectOne({
      method: 'PATCH',
      url: '/api/v1/catalog/services/service-1',
    }).flush({
      id: 'service-1',
      code: 'DIAG-1',
      name: 'Diagnóstico actualizado',
      price: 12000,
      duration_minutes: 45,
      active: true,
    });
    requests.expectOne('/api/v1/inventory/parts').flush([]);
    requests.expectOne('/api/v1/catalog/services?active=true').flush([
      {
        id: 'service-1',
        code: 'DIAG-1',
        name: 'Diagnóstico actualizado',
        price: 12000,
        duration_minutes: 45,
        active: true,
      },
    ]);

    expect(component.managementRecords()[0]['name']).toBe('Diagnóstico actualizado');
    expect(component.rows()[0].primary).toBe('Diagnóstico actualizado');
    expect(component.message()).toBe(component.t('recordUpdated'));
    requests.verify();
  });

  it('associates API validation errors with the matching edit control', () => {
    const fixture = TestBed.createComponent(WorkspacePageComponent);
    fixture.detectChanges();
    const requests = TestBed.inject(HttpTestingController);
    requests.expectOne('/api/v1/work-orders').flush([]);

    const component = fixture.componentInstance;
    component.page.set('catalog');
    component.managementRecords.set([
      { id: 'service-1', code: 'DIAG-1', name: 'Diagnóstico', price: 10000, duration_minutes: 30, active: true },
    ]);
    component.editRecord('service-1');
    fixture.detectChanges();
    component.editForm.price = -1;
    component.saveRecord();

    requests.expectOne({
      method: 'PATCH',
      url: '/api/v1/catalog/services/service-1',
    }).flush({
      detail: [{ loc: ['body', 'price'], msg: 'Input should be greater than 0', type: 'greater_than' }],
    }, { status: 422, statusText: 'Unprocessable Entity' });
    fixture.detectChanges();

    const price = fixture.nativeElement.querySelector('#edit-service-price') as HTMLInputElement;
    expect(price.getAttribute('aria-invalid')).toBe('true');
    expect(price.getAttribute('aria-describedby')).toBe('edit-service-price-error');
    expect(fixture.nativeElement.querySelector('#edit-service-price-error')?.textContent).toContain('Input should be greater than 0');

    component.clearEditFieldError('price');
    fixture.detectChanges();
    expect(price.hasAttribute('aria-invalid')).toBe(false);
    expect(fixture.nativeElement.querySelector('#edit-service-price-error')).toBeNull();
    requests.verify();
  });
});
