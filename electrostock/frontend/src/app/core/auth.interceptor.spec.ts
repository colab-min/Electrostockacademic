import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { authInterceptor } from './auth.interceptor';
import { SessionService } from './session.service';

describe('authInterceptor', () => {
  let httpTesting: HttpTestingController;
  let session: SessionService;

  beforeEach(() => {
    localStorage.setItem('electrostock.accessToken', 'expired');
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    httpTesting = TestBed.inject(HttpTestingController);
    session = TestBed.inject(SessionService);
    session.accessToken.set('expired');
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.removeItem('electrostock.accessToken');
    localStorage.removeItem('electrostock.user');
  });

  it('renews an expired access token and retries the protected request', () => {
    let response: unknown;
    TestBed.inject(HttpClient).get('/api/v1/work-orders').subscribe((value) => {
      response = value;
    });

    const firstRequest = httpTesting.expectOne('/api/v1/work-orders');
    expect(firstRequest.request.headers.get('Authorization')).toBe('Bearer expired');
    firstRequest.flush({ detail: 'Token expired' }, { status: 401, statusText: 'Unauthorized' });

    const refreshRequest = httpTesting.expectOne('/api/v1/auth/refresh');
    expect(refreshRequest.request.withCredentials).toBe(true);
    expect(refreshRequest.request.headers.has('Authorization')).toBe(false);
    refreshRequest.flush({ access_token: 'fresh', token_type: 'bearer' });

    const retryRequest = httpTesting.expectOne('/api/v1/work-orders');
    expect(retryRequest.request.headers.get('Authorization')).toBe('Bearer fresh');
    retryRequest.flush([{ number: 'OT-000001' }]);

    expect(response).toEqual([{ number: 'OT-000001' }]);
    expect(session.accessToken()).toBe('fresh');
    expect(localStorage.getItem('electrostock.accessToken')).toBeNull();
  });
});
