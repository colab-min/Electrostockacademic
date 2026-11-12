import { Component, computed, ElementRef, inject, signal, ViewChild } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { ActivatedRoute, NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

import { I18nService, TranslationKey } from '../../core/i18n.service';
import { SessionService } from '../../core/session.service';

interface NavigationItem {
  label: TranslationKey;
  path: string;
}

@Component({
  imports: [RouterLink, RouterOutlet],
  selector: 'app-root',
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly documentTitle = inject(Title);
  @ViewChild('mainContent') private mainContent?: ElementRef<HTMLElement>;
  readonly session = inject(SessionService);
  readonly i18n = inject(I18nService);
  readonly isPublicPage = signal(false);
  readonly navigation = computed<NavigationItem[]>(() => {
    const role = this.session.user()?.role;
    if (role === 'CUSTOMER') {
      return [
        { label: 'customerAppointments', path: '/cliente/citas' },
        { label: 'createAppointment', path: '/cliente/agendar' },
        { label: 'customerVehicles', path: '/cliente/vehiculos/nuevo' },
      ];
    }
    if (role === 'RECEPTIONIST') {
      return [
        { label: 'appointments', path: '/recepcion/agenda' },
        { label: 'entry', path: '/recepcion/ingreso' },
        { label: 'createOrder', path: '/recepcion/ordenes/nueva' },
        { label: 'registerCustomer', path: '/recepcion/clientes/nuevo' },
      ];
    }
    if (role === 'MECHANIC') {
      return [
        { label: 'workOrders', path: '/taller/bahia' },
        { label: 'vehicles', path: '/taller/vehiculos/expediente' },
      ];
    }
    if (role === 'ADMIN') {
      return [
        { label: 'pageReports', path: '/admin/indicadores' },
        { label: 'assignMechanic', path: '/admin/asignacion' },
        { label: 'customers', path: '/admin/clientes' },
        { label: 'vehicles', path: '/admin/vehiculos' },
        { label: 'inventory', path: '/admin/inventario' },
        { label: 'catalog', path: '/admin/catalogo' },
        { label: 'users', path: '/admin/usuarios' },
        { label: 'reports', path: '/admin/bitacora' },
      ];
    }
    return [];
  });

  constructor() {
    this.isPublicPage.set(this.isPublicRoute());
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe(() => {
      this.isPublicPage.set(this.isPublicRoute());
      this.updateDocumentTitle();
      queueMicrotask(() => this.mainContent?.nativeElement.focus());
    });
    this.updateDocumentTitle();
  }

  t(key: TranslationKey): string {
    return this.i18n.translate(key);
  }

  homePath(): string {
    const role = this.session.user()?.role;
    if (role === 'ADMIN') return '/admin/indicadores';
    if (role === 'RECEPTIONIST') return '/recepcion/agenda';
    if (role === 'MECHANIC') return '/taller/bahia';
    if (role === 'CUSTOMER') return '/cliente/citas';
    return '/ingresar';
  }

  changeLocale(event: Event): void {
    const locale = (event.target as HTMLSelectElement).value;
    this.i18n.setLocale(locale === 'en' ? 'en' : 'es-CO');
    this.updateDocumentTitle();
  }

  roleLabel(): string {
    const role = this.session.user()?.role;
    if (role === 'ADMIN') return this.t('admin');
    if (role === 'RECEPTIONIST') return this.t('receptionist');
    if (role === 'MECHANIC') return this.t('mechanic');
    return this.t('customer');
  }

  logout(): void {
    this.session.logout();
    void this.router.navigateByUrl('/ingresar');
  }

  private updateDocumentTitle(): void {
    const url = this.router.url;
    let page: string | undefined;
    let route: ActivatedRoute | null = this.route;
    while (route) {
      page = route.snapshot.data['page'] ?? page;
      route = route.firstChild;
    }

    const pageTitleKeys: Record<string, TranslationKey> = {
      appointments: 'pageAppointments',
      catalog: 'pageCatalog',
      customers: 'pageCustomers',
      dashboard: 'pageDashboard',
      inventory: 'pageInventory',
      reports: 'pageReports',
      tracking: 'pageTracking',
      vehicles: 'pageVehicles',
      workOrders: 'pageWorkOrders',
      users: 'users',
    };
    let routeTitleKey: TranslationKey | undefined;
    if (url.includes('/registro')) routeTitleKey = 'register';
    else if (url.includes('/ingresar')) routeTitleKey = 'signIn';
    else if (url.startsWith('/encuesta/')) routeTitleKey = 'pageSurvey';
    else if (url.includes('/cliente/agendar')) routeTitleKey = 'createAppointment';
    else if (url.includes('/cliente/citas/') && url.includes('/reprogramar')) routeTitleKey = 'appointmentReschedule';
    else if (url.includes('/cliente/citas')) routeTitleKey = 'customerAppointments';
    else if (url.includes('/cliente/vehiculos')) {
      routeTitleKey = url.includes('/historial') ? 'vehicleRecord' : 'customerVehicles';
    } else if (url.includes('/admin/asignacion')) routeTitleKey = 'mechanicAssignment';
    else if (url.includes('/admin/clientes')) routeTitleKey = 'pageCustomers';
    else if (url.includes('/admin/vehiculos')) routeTitleKey = 'pageVehicles';
    else if (url.includes('/admin/bitacora')) routeTitleKey = 'reports';
    else if (url.includes('/taller/bahia')) routeTitleKey = 'bay';
    else if (url.includes('/taller/ordenes/')) routeTitleKey = 'workOrderDetail';
    else if (url.includes('/recepcion/clientes/')) routeTitleKey = 'registerCustomer';
    else if (url.includes('/recepcion/ordenes/') && url.includes('/cobro')) routeTitleKey = 'paymentAndDelivery';
    else if (url.includes('/recepcion/ordenes/')) routeTitleKey = 'createOrder';
    else if (url.includes('/recepcion/ingreso')) routeTitleKey = 'createWalkIn';
    else if (url.includes('/recepcion/agenda')) routeTitleKey = 'appointments';
    else routeTitleKey = pageTitleKeys[page ?? ''];
    const titleKey = routeTitleKey ?? 'app';
    const title = this.t(titleKey);
    this.documentTitle.setTitle(titleKey === 'app' ? title : `${title} | ${this.t('app')}`);
  }

  private isPublicRoute(): boolean {
    const url = this.router.url.split('?')[0];
    return ['/ingresar', '/registro'].includes(url) || url.startsWith('/encuesta/');
  }
}
