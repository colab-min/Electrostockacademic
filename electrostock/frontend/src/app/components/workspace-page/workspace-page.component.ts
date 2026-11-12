import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, inject, OnDestroy, signal, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, NavigationEnd, Router } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs';

import { MetricCardComponent } from '../metric-card/metric-card.component';
import { StatusBadgeComponent } from '../status-badge/status-badge.component';
import { ApiService } from '../../core/api.service';
import { ApiRecord, DisplayRow } from '../../core/models';
import { I18nService, TranslationKey } from '../../core/i18n.service';
import { SessionService } from '../../core/session.service';

const pageTitles: Record<string, TranslationKey> = {
  dashboard: 'pageDashboard',
  appointments: 'pageAppointments',
  customers: 'pageCustomers',
  vehicles: 'pageVehicles',
  inventory: 'pageInventory',
  workOrders: 'pageWorkOrders',
  catalog: 'pageCatalog',
  reports: 'pageReports',
  tracking: 'pageTracking',
  survey: 'pageSurvey',
  users: 'users',
};

function isRecord(value: unknown): value is ApiRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

interface ReportStatus {
  status: string;
  count: number;
}

interface ManagementForm {
  full_name: string;
  document_type: string;
  document_number: string;
  phone: string;
  email: string;
  customer_id: string;
  serial_number: string;
  plate: string;
  brand: string;
  model: string;
  year: number | null;
  battery_capacity_ah: number | null;
  cell_type: string;
  motor_power_w: number | null;
  controller: string;
  code: string;
  name: string;
  description: string;
  price: number;
  duration_minutes: number;
  sku: string;
  category: string;
  voltage: string;
  unit_price: number;
  min_threshold: number;
  role: string;
  active: boolean;
}

function emptyManagementForm(): ManagementForm {
  return {
    full_name: '',
    document_type: 'CC',
    document_number: '',
    phone: '',
    email: '',
    customer_id: '',
    serial_number: '',
    plate: '',
    brand: '',
    model: '',
    year: null,
    battery_capacity_ah: null,
    cell_type: '',
    motor_power_w: null,
    controller: '',
    code: '',
    name: '',
    description: '',
    price: 0,
    duration_minutes: 30,
    sku: '',
    category: '',
    voltage: '',
    unit_price: 0,
    min_threshold: 0,
    role: 'MECHANIC',
    active: true,
  };
}

@Component({
  imports: [FormsModule, MetricCardComponent, StatusBadgeComponent],
  standalone: true,
  styleUrl: './workspace-page.component.css',
  templateUrl: './workspace-page.component.html',
})
export class WorkspacePageComponent implements OnDestroy {
  readonly session = inject(SessionService);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly i18n = inject(I18nService);
  readonly page = signal('dashboard');
  readonly titleKey = signal<TranslationKey>('pageDashboard');
  readonly rows = signal<DisplayRow[]>([]);
  readonly managementRecords = signal<ApiRecord[]>([]);
  readonly editingRecord = signal<ApiRecord | null>(null);
  readonly includeInactiveRecords = signal(false);
  readonly vehicles = signal<ApiRecord[]>([]);
  readonly services = signal<ApiRecord[]>([]);
  readonly slots = signal<ApiRecord[]>([]);
  readonly parts = signal<ApiRecord[]>([]);
  readonly customers = signal<ApiRecord[]>([]);
  readonly mechanics = signal<ApiRecord[]>([]);
  readonly workOrderDetail = signal<ApiRecord | null>(null);
  readonly vehicleRecord = signal<ApiRecord | null>(null);
  readonly servicePartRows = signal<ApiRecord[]>([]);
  readonly servicePartDraft = signal<{ part_id: string; quantity: number }[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly editFieldErrors = signal<Record<string, string>>({});
  readonly workOrderFaultTypeError = signal(false);
  readonly message = signal('');
  readonly trackingState = signal<ApiRecord | null>(null);
  readonly trackingLive = signal(false);
  readonly holdRemainingSeconds = signal<number | null>(null);
  readonly surveyData = signal<ApiRecord | null>(null);
  readonly paymentReceipt = signal<ApiRecord | null>(null);
  readonly surveyToken = signal('');
  readonly surveyScores = [1, 2, 3, 4, 5];
  readonly bookingSteps: TranslationKey[] = ['stepVehicle', 'stepService', 'stepSlot', 'stepReview'];
  readonly bookingStep = signal(1);

  vehicleId = '';
  customerId = '';
  serviceId = '';
  slotId = '';
  rescheduleSlotId = '';
  serialNumber = '';
  brand = '';
  model = '';
  plate = '';
  vehicleYear: number | null = null;
  batteryCapacityAh: number | null = null;
  cellType = '';
  motorPowerW: number | null = null;
  controller = '';
  customerName = '';
  documentType = 'CC';
  documentNumber = '';
  customerPhone = '';
  customerEmail = '';
  dataConsent = false;
  partId = '';
  movementType = 'IN';
  quantity = 1;
  reason = '';
  partSku = '';
  partName = '';
  partCategory = '';
  partVoltage = '';
  partUnitPrice = 0;
  initialStock = 0;
  minThreshold = 0;
  servicePartId = '';
  servicePartQuantity = 1;
  appointmentCode = '';
  faultDescription = '';
  workOrderFaultType = '';
  appointmentCancelReason = '';
  selectedId = '';
  mechanicId = '';
  nextStatus = 'DIAGNOSING';
  statusReason = '';
  diagnosis = '';
  workOrderPartId = '';
  workOrderPartQuantity = 1;
  workOrderServiceId = '';
  expectedPartId = '';
  expectedPartDate = '';
  noteText = '';
  trackingCode = '';
  serviceCode = '';
  serviceName = '';
  serviceDescription = '';
  servicePrice = 1;
  serviceDuration = 30;
  internalUserName = '';
  internalUserEmail = '';
  internalUserRole = 'MECHANIC';
  internalUserPassword = '';
  currentPassword = '';
  newPassword = '';
  paymentMethod = 'CASH';
  surveyScore = 5;
  surveyComment = '';
  private paymentIdempotencyKey = crypto.randomUUID();
  private walkInIdempotencyKey =
    sessionStorage.getItem('electrostock.walkInIdempotencyKey') ?? crypto.randomUUID();
  private trackingStream?: EventSource;
  private holdCountdown?: ReturnType<typeof setInterval>;
  @ViewChild('editRecordHeading') private editRecordHeading?: ElementRef<HTMLElement>;
  @ViewChild('recordsHeading') private recordsHeading?: ElementRef<HTMLElement>;
  editForm = emptyManagementForm();

  constructor() {
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      takeUntilDestroyed(inject(DestroyRef)),
    ).subscribe(() => {
      this.updatePage();
      this.load();
    });
    this.updatePage();
    this.load();
  }

  ngOnDestroy(): void {
    this.trackingStream?.close();
    this.stopHoldCountdown();
  }

  t(key: TranslationKey): string {
    return this.i18n.translate(key);
  }

  roleLabel(): string {
    const role = this.session.user()?.role;
    if (role === 'ADMIN') return this.t('admin');
    if (role === 'RECEPTIONIST') return this.t('receptionist');
    if (role === 'MECHANIC') return this.t('mechanic');
    return this.t('customer');
  }

  isAuditPage(): boolean {
    return this.router.url.includes('/bitacora');
  }

  isCustomerBookingPage(): boolean {
    return this.router.url.includes('/cliente/agendar');
  }

  view(): string {
    const role = this.session.user()?.role;
    if (this.page() === 'reports') return this.isAuditPage() ? 'audit-log' : 'indicators';
    if (this.page() === 'survey') return 'customer-survey';
    if (this.page() === 'appointments' && role === 'CUSTOMER') {
      return this.isCustomerBookingPage() ? 'customer-booking' : 'customer-appointments';
    }
    if (this.page() === 'appointments' && role !== 'CUSTOMER') return 'reception-calendar';
    if (this.page() === 'vehicles' && role === 'CUSTOMER') {
      return this.isCustomerHistoryPage() ? 'customer-history' : 'customer-vehicles';
    }
    if (this.page() === 'vehicles' && this.isCustomerRegistrationPage()) return 'customer-registration';
    if (this.page() === 'vehicles') return 'technical-file';
    if (this.page() === 'workOrders') {
      if (this.isPaymentPage()) return 'reception-payment';
      if (role === 'ADMIN') return 'admin-assignment';
      if (role === 'MECHANIC') return this.router.url.includes('/taller/ordenes/') ? 'mechanic-order-detail' : 'mechanic-bay';
      if (this.isWalkInPage()) return 'reception-intake';
      return 'reception-orders';
    }
    if (this.page() === 'catalog') return 'service-catalog';
    if (this.page() === 'users') return 'user-management';
    return this.page();
  }

  isCustomerHistoryPage(): boolean {
    return this.router.url.includes('/cliente/vehiculos/') && this.router.url.includes('/historial');
  }

  openCustomerVehicleRegistration(): void {
    void this.router.navigateByUrl('/cliente/vehiculos/nuevo');
  }

  reportTotal(): number {
    return this.reportNumber('orders total');
  }

  totalAvailableStock(): number {
    return this.parts().reduce((total, part) => total + this.availablePartStock(part), 0);
  }

  lowStockParts(): ApiRecord[] {
    return this.parts().filter((part) => this.availablePartStock(part) <= this.numericValue(part['min_threshold']));
  }

  customerPendingConfirmations(): number {
    return this.rows().filter((row) => ['HELD', 'PENDING_CONFIRMATION'].includes(row.status)).length;
  }

  reportActiveTotal(): number {
    return this.reportStatuses()
      .filter(({ status }) => !['FINISHED', 'DELIVERED', 'CANCELLED'].includes(status))
      .reduce((total, item) => total + item.count, 0);
  }

  reportCompletedTotal(): number {
    return this.reportStatuses()
      .filter(({ status }) => ['FINISHED', 'DELIVERED'].includes(status))
      .reduce((total, item) => total + item.count, 0);
  }

  reportStatuses(): ReportStatus[] {
    const value = this.reportRow('orders by status')?.secondary;
    if (!value) return [];

    return value.split(' · ').flatMap((entry) => {
      const separator = entry.lastIndexOf(':');
      if (separator < 1) return [];
      const count = Number(entry.slice(separator + 1).trim());
      if (!Number.isFinite(count) || count < 0) return [];
      return [{ status: entry.slice(0, separator).trim().toUpperCase(), count }];
    });
  }

  reportStatusShare(count: number): number {
    const maximum = Math.max(...this.reportStatuses().map((item) => item.count), 0);
    return maximum === 0 ? 0 : (count / maximum) * 100;
  }

  reportDate(field: 'from' | 'to'): string {
    return this.reportRow(field)?.secondary ?? '—';
  }

  isPaymentPage(): boolean {
    return this.router.url.includes('/cobro');
  }

  paymentSubtotal(): number {
    const serviceTotal = this.workOrderServices().reduce((total, service) => total + this.numericValue(service['applied_price']), 0);
    const partTotal = this.workOrderParts()
      .filter((part) => part['status'] === 'INSTALLED')
      .reduce((total, part) => total + this.numericValue(part['unit_price']) * this.numericValue(part['quantity']), 0);
    return serviceTotal + partTotal;
  }

  numericForDisplay(value: unknown): number {
    return this.numericValue(value);
  }

  paymentTax(): number {
    return this.paymentSubtotal() * 0.19;
  }

  paymentTotal(): number {
    return this.roundHalfEven(Math.round(this.paymentSubtotal() * 100) * 119, 10000);
  }

  paymentOrderStatus(): string {
    const order = this.workOrderDetail()?.['order'];
    return isRecord(order) && typeof order['status'] === 'string' ? order['status'] : '';
  }

  paymentOrderNumber(): string {
    const order = this.workOrderDetail()?.['order'];
    return isRecord(order) && typeof order['number'] === 'string' ? order['number'] : '';
  }

  headingEyebrow(): string {
    return this.page() === 'survey' ? this.t('app') : this.session.user()?.full_name ?? this.t('app');
  }

  openPayment(orderId: string): void {
    void this.router.navigateByUrl(`/recepcion/ordenes/${encodeURIComponent(orderId)}/cobro`);
  }

  onPaymentOrderChange(): void {
    this.paymentReceipt.set(null);
    this.loadOrderDetails();
  }

  registerPayment(): void {
    if (!this.selectedId) return this.showMissingFields(['selectedRecord']);
    if (this.paymentOrderStatus() !== 'PENDING_PAYMENT') {
      return this.showRequired(this.t('orderMustBePendingPayment'));
    }
    if (this.paymentTotal() <= 0) return this.showRequired(this.t('noBillableItems'));
    this.error.set('');
    this.message.set('');
    this.api.postWithHeaders<ApiRecord>(
      `/work-orders/${encodeURIComponent(this.selectedId)}/payments`,
      { amount: this.paymentTotal(), method: this.paymentMethod },
      { 'Idempotency-Key': this.paymentIdempotencyKey },
    ).subscribe({
      next: (receipt) => {
        this.paymentReceipt.set(receipt);
        this.paymentIdempotencyKey = crypto.randomUUID();
        this.message.set(`${this.t('paymentRegistered')} ${String(receipt['receipt_number'] ?? '')}`.trim());
        this.load(true);
        this.loadOrderDetails();
      },
      error: (error: HttpErrorResponse) => this.error.set(this.errorMessage(error)),
    });
  }

  deliverWorkOrder(): void {
    if (!this.selectedId) return this.showMissingFields(['selectedRecord']);
    this.error.set('');
    this.message.set('');
    this.api.post<ApiRecord>(`/work-orders/${encodeURIComponent(this.selectedId)}/delivery`, {}).subscribe({
      next: (response) => {
        const token = response['survey_token'];
        if (typeof token !== 'string' || !token) {
          this.error.set(this.t('unexpectedResponse'));
          return;
        }
        this.surveyToken.set(token);
        this.message.set(this.t('orderDelivered'));
        this.load(true);
        this.loadOrderDetails();
      },
      error: (error: HttpErrorResponse) => this.error.set(this.errorMessage(error)),
    });
  }

  submitSurvey(): void {
    const token = this.surveyToken();
    if (!token) return this.showRequired(this.t('loadError'));
    this.error.set('');
    this.message.set('');
    this.api.post<ApiRecord>(`/surveys/${encodeURIComponent(token)}`, {
      score: this.surveyScore,
      comment: this.surveyComment.trim() || null,
    }).subscribe({
      next: (response) => {
        this.surveyData.set(response);
        this.message.set(this.t('surveySaved'));
      },
      error: (error: HttpErrorResponse) => this.error.set(this.errorMessage(error)),
    });
  }

  load(preserveMessage = false): void {
    this.error.set('');
    if (!preserveMessage) this.message.set('');
    this.loading.set(true);
    this.trackingStream?.close();
    this.trackingStream = undefined;
    this.trackingLive.set(false);
    this.trackingState.set(null);
    this.surveyData.set(null);
    this.managementRecords.set([]);
    const user = this.session.user();
    const page = this.page();
    if (page !== 'appointments') this.stopHoldCountdown();
    this.loadOptions(page, user?.role);
    let path = '/work-orders';
    if (page === 'appointments') {
      path = user?.role === 'CUSTOMER' ? '/scheduling/appointments/mine' : '/scheduling/appointments';
    } else if (page === 'vehicles') {
      const vehicleRouteId = this.route.snapshot.paramMap.get('id');
      if (vehicleRouteId && this.router.url.includes('/historial')) {
        path = `/me/vehicles/${encodeURIComponent(vehicleRouteId)}/history`;
        this.vehicleId = vehicleRouteId;
        this.loadVehicleRecord(vehicleRouteId);
      } else {
        path = user?.role === 'CUSTOMER' ? '/vehicles/mine' : '/vehicles';
      }
    } else if (page === 'inventory') {
      path = `/inventory/parts?active=${this.includeInactiveRecords() ? 'false' : 'true'}`;
    } else if (page === 'catalog') {
      path = `/catalog/services?active=${this.includeInactiveRecords() ? 'false' : 'true'}`;
    } else if (page === 'customers') {
      path = '/customers';
    } else if (page === 'reports') {
      path = this.router.url.includes('bitacora') ? '/audit' : this.reportSummaryPath();
    } else if (page === 'survey') {
      const token = this.route.snapshot.paramMap.get('token');
      if (!token) {
        this.loading.set(false);
        this.error.set(this.t('loadError'));
        return;
      }
      this.surveyToken.set(token);
      path = `/surveys/${encodeURIComponent(token)}`;
    } else if (page === 'tracking') {
      const code = this.route.snapshot.paramMap.get('code');
      if (!code || code === 'demo') {
        this.loading.set(false);
        return;
      }
      this.trackingCode = code;
      path = `/tracking/${encodeURIComponent(code)}`;
    } else if (page === 'users') {
      path = `/users?active=${this.includeInactiveRecords() ? 'false' : 'true'}`;
    } else if (page === 'workOrders' && this.isPaymentPage()) {
      const orderId = this.route.snapshot.paramMap.get('id');
      if (orderId) {
        this.selectedId = orderId;
        this.loadOrderDetails(orderId);
      }
    } else if (user?.role === 'CUSTOMER') {
      path = '/scheduling/appointments/mine';
    } else if (user?.role === 'MECHANIC') {
      path = '/work-orders/mine';
    } else if (user?.role === 'RECEPTIONIST' && this.router.url.includes('/recepcion/ingreso')) {
      path = '/scheduling/walk-ins/queue';
    }

    this.api.get<unknown>(path).subscribe({
      next: (data) => {
        this.rows.set(this.toRows(data));
        if (this.isCrudPage()) this.managementRecords.set(this.toRecords(data));
        if (page === 'tracking' && isRecord(data)) {
          this.trackingState.set(data);
          this.openTrackingStream(this.trackingCode);
        }
        if (page === 'survey' && isRecord(data)) this.surveyData.set(data);
        this.loading.set(false);
      },
      error: (error: HttpErrorResponse) => {
        this.loading.set(false);
        this.error.set(error.status === 401 ? this.t('notAuthorized') : this.t('loadError'));
      },
    });
  }

  createAppointment(): void {
    if (!this.vehicleId || !this.serviceId || !this.slotId) {
      return this.showRequired(
        [!this.vehicleId && this.t('chooseVehicle'), !this.serviceId && this.t('chooseService'), !this.slotId && this.t('chooseSlot')]
          .filter(Boolean)
          .join(' '),
      );
    }
    this.perform(
      this.api.post('/scheduling/appointments', {
        vehicle_id: this.vehicleId,
        service_id: this.serviceId,
        slot_id: this.slotId,
      }),
    );
  }

  nextBookingStep(): void {
    if (this.bookingStep() === 1 && !this.vehicleId) return this.showMissingFields(['chooseVehicle']);
    if (this.bookingStep() === 2 && !this.serviceId) return this.showMissingFields(['chooseService']);
    if (this.bookingStep() === 3 && !this.slotId) return this.showMissingFields(['chooseSlot']);
    this.bookingStep.update((step) => Math.min(step + 1, this.bookingSteps.length));
    this.message.set('');
  }

  previousBookingStep(): void {
    this.bookingStep.update((step) => Math.max(step - 1, 1));
    this.message.set('');
  }

  selectedBookingVehicle(): string {
    const vehicle = this.vehicles().find((item) => item.id === this.vehicleId);
    return vehicle ? `${vehicle.brand} ${vehicle.model} · ${vehicle.serial_number}` : '—';
  }

  selectedBookingService(): string {
    const service = this.services().find((item) => item.id === this.serviceId);
    return service ? `${String(service.name ?? '')} · ${this.formatCurrency(service.price)}` : '—';
  }

  selectedBookingSlot(): string {
    const slot = this.slots().find((item) => item.id === this.slotId);
    return slot ? `${String(slot.date ?? '')} · ${String(slot.start_time ?? '')}` : '—';
  }

  rescheduleAppointment(): void {
    if (!this.selectedId || !this.rescheduleSlotId) {
      return this.showMissingFields([
        ...(!this.selectedId ? ['selectedRecord' as TranslationKey] : []),
        ...(!this.rescheduleSlotId ? ['chooseSlot' as TranslationKey] : []),
      ]);
    }
    this.perform(
      this.api.post(`/scheduling/appointments/${encodeURIComponent(this.selectedId)}/reschedule`, {
        slot_id: this.rescheduleSlotId,
      }),
    );
  }

  createVehicle(): void {
    const missing = [
      !this.serialNumber && 'serial',
      !this.brand && 'brand',
      !this.model && 'model',
      this.session.user()?.role !== 'CUSTOMER' && !this.customerId && 'chooseCustomer',
    ].filter((field): field is TranslationKey => Boolean(field));
    if (missing.length) return this.showMissingFields(missing);
    this.perform(
      this.api.post('/vehicles', {
        customer_id: this.customerId || undefined,
        serial_number: this.serialNumber,
        brand: this.brand,
        model: this.model,
        plate: this.plate || undefined,
        year: this.vehicleYear || undefined,
        battery_capacity_ah: this.batteryCapacityAh || undefined,
        cell_type: this.cellType || undefined,
        motor_power_w: this.motorPowerW || undefined,
        controller: this.controller || undefined,
      }),
      false,
      undefined,
      undefined,
      'recordCreated',
    );
  }

  createCustomer(): void {
    this.error.set('');
    this.message.set('');
    const required: TranslationKey[] = [];
    if (!this.customerName.trim()) required.push('customerName');
    if (!this.documentNumber.trim()) required.push('documentNumber');
    if (!this.customerPhone.trim()) required.push('phone');
    if (!this.dataConsent) return this.showRequired(this.t('consentRequired'));
    if (required.length) return this.showMissingFields(required);
    this.saving.set(true);
    this.api.post<ApiRecord>('/customers', {
      full_name: this.customerName.trim(),
      document_type: this.documentType,
      document_number: this.documentNumber.trim(),
      phone: this.customerPhone.trim(),
      email: this.customerEmail.trim() || null,
      data_consent: this.dataConsent,
    }).subscribe({
      next: (customer) => {
        this.saving.set(false);
        if (customer.id) this.customerId = customer.id;
        this.message.set(this.t(this.page() === 'customers' ? 'recordCreated' : 'customerSaved'));
        this.load(true);
      },
      error: (error: HttpErrorResponse) => {
        this.saving.set(false);
        this.error.set(this.errorMessage(error));
      },
    });
  }

  recordMovement(): void {
    const missing = [
      !this.partId && 'choosePart',
      !this.reason && 'reason',
      this.quantity < 1 && 'quantity',
    ].filter((field): field is TranslationKey => Boolean(field));
    if (missing.length) return this.showMissingFields(missing);
    this.perform(
      this.api.post('/inventory/movements', {
        part_id: this.partId,
        type: this.movementType,
        quantity: this.quantity,
        reason: this.reason,
      }),
    );
  }

  createPart(): void {
    if (!this.partSku.trim() || !this.partName.trim()) {
      return this.showMissingFields([
        ...(!this.partSku.trim() ? ['sku' as TranslationKey] : []),
        ...(!this.partName.trim() ? ['partName' as TranslationKey] : []),
      ]);
    }
    this.perform(this.api.post('/inventory/parts', {
      sku: this.partSku.trim(),
      name: this.partName.trim(),
      category: this.partCategory.trim() || 'General',
      voltage: this.partVoltage.trim() || null,
      unit_price: this.partUnitPrice,
      physical_stock: this.initialStock,
      min_threshold: this.minThreshold,
    }), false, undefined, undefined, 'recordCreated');
  }

  createWorkOrder(): void {
    if (!this.vehicleId && !this.appointmentCode) return this.showRequired(this.t('vehicleOrAppointmentRequired'));
    const isWalkIn = this.router.url.includes('/recepcion/ingreso') && !this.appointmentCode;
    if (!this.appointmentCode && !this.workOrderServiceId) return this.showMissingFields(['chooseService']);
    if (isWalkIn && !this.workOrderFaultType) {
      this.workOrderFaultTypeError.set(true);
      return this.showRequired(this.t('faultTypeRequired'));
    }
    this.workOrderFaultTypeError.set(false);
    const payload = {
      vehicle_id: this.vehicleId || null,
      appointment_code: this.appointmentCode || null,
      service_id: this.workOrderServiceId || null,
      fault_description: this.faultDescription,
      fault_type: this.workOrderFaultType || null,
    };
    if (isWalkIn) {
      sessionStorage.setItem('electrostock.walkInIdempotencyKey', this.walkInIdempotencyKey);
      this.perform(
        this.api.postWithHeaders(
          '/scheduling/walk-ins',
          payload,
          { 'Idempotency-Key': this.walkInIdempotencyKey },
        ),
        false,
        () => {
          this.walkInIdempotencyKey = crypto.randomUUID();
          sessionStorage.removeItem('electrostock.walkInIdempotencyKey');
        },
        (error) => {
          if (error.status === 409) {
            this.walkInIdempotencyKey = crypto.randomUUID();
            sessionStorage.removeItem('electrostock.walkInIdempotencyKey');
          }
        },
      );
      return;
    }
    this.perform(this.api.post('/work-orders', payload));
  }

  changeStatus(): void {
    if (!this.selectedId) return this.showMissingFields(['selectedRecord']);
    this.perform(
      this.api.patch(`/work-orders/${encodeURIComponent(this.selectedId)}/status`, {
        status: this.nextStatus,
        reason: this.statusReason || undefined,
        expected_part_id: this.nextStatus === 'PENDING_INSTALLATION' ? this.expectedPartId : undefined,
        expected_part_date: this.nextStatus === 'PENDING_INSTALLATION' ? this.expectedPartDate || undefined : undefined,
      }),
    );
  }

  assignMechanic(): void {
    if (!this.selectedId || !this.mechanicId) {
      const missing: TranslationKey[] = [];
      if (!this.selectedId) missing.push('selectedRecord');
      if (!this.mechanicId) missing.push('mechanic');
      return this.showMissingFields(missing);
    }
    const selected = this.rows().find((row) => row.id === this.selectedId);
    if (!selected) return this.showMissingFields(['selectedRecord']);
    this.perform(
      this.api.patch(`/work-orders/${encodeURIComponent(this.selectedId)}/assignment`, {
        mechanic_id: this.mechanicId,
        version: selected.version ?? 1,
      }),
    );
  }

  saveDiagnosis(): void {
    if (!this.selectedId || !this.diagnosis.trim()) {
      const missing: TranslationKey[] = [];
      if (!this.selectedId) missing.push('selectedRecord');
      if (!this.diagnosis.trim()) missing.push('diagnosis');
      return this.showMissingFields(missing);
    }
    this.perform(
      this.api.put(`/work-orders/${encodeURIComponent(this.selectedId)}/diagnosis`, {
        diagnosis: this.diagnosis.trim(),
      }),
    );
  }

  loadOrderDetails(orderId = this.selectedId): void {
    if (!orderId) {
      this.workOrderDetail.set(null);
      return;
    }
    this.api.get<unknown>(`/work-orders/${encodeURIComponent(orderId)}`).subscribe({
      next: (data) => this.workOrderDetail.set(isRecord(data) ? data : null),
      error: (error: HttpErrorResponse) => this.error.set(this.errorMessage(error)),
    });
  }

  addPartToOrder(): void {
    if (!this.selectedId || !this.workOrderPartId) {
      return this.showMissingFields([
        ...(!this.selectedId ? ['selectedRecord' as TranslationKey] : []),
        ...(!this.workOrderPartId ? ['choosePart' as TranslationKey] : []),
      ]);
    }
    this.perform(this.api.post(`/work-orders/${encodeURIComponent(this.selectedId)}/parts`, {
      part_id: this.workOrderPartId,
      quantity: this.workOrderPartQuantity,
    }));
  }

  installPart(lineId: string): void {
    if (!this.selectedId) return this.showMissingFields(['selectedRecord']);
    this.perform(this.api.post(`/work-orders/${encodeURIComponent(this.selectedId)}/parts/${encodeURIComponent(lineId)}/install`, {}));
  }

  removePart(lineId: string): void {
    if (!this.selectedId) return this.showMissingFields(['selectedRecord']);
    this.perform(this.api.post(`/work-orders/${encodeURIComponent(this.selectedId)}/parts/${encodeURIComponent(lineId)}/remove`, {}));
  }

  addServiceToOrder(): void {
    if (!this.selectedId || !this.workOrderServiceId) {
      return this.showMissingFields([
        ...(!this.selectedId ? ['selectedRecord' as TranslationKey] : []),
        ...(!this.workOrderServiceId ? ['chooseService' as TranslationKey] : []),
      ]);
    }
    this.perform(this.api.post(`/work-orders/${encodeURIComponent(this.selectedId)}/services`, {
      service_id: this.workOrderServiceId,
    }));
  }

  readmitOrder(): void {
    if (!this.selectedId) return this.showMissingFields(['selectedRecord']);
    this.perform(
      this.api.post(`/work-orders/${encodeURIComponent(this.selectedId)}/readmission`, {}),
    );
  }

  settleOrder(): void {
    if (!this.selectedId) return this.showMissingFields(['selectedRecord']);
    this.perform(
      this.api.post(`/work-orders/${encodeURIComponent(this.selectedId)}/settlement`, {}),
    );
  }

  confirmAppointment(): void {
    if (!this.selectedId) return this.showMissingFields(['selectedRecord']);
    this.perform(
      this.api.post(`/scheduling/appointments/${encodeURIComponent(this.selectedId)}/confirm`, {}),
    );
  }

  cancelAppointment(): void {
    if (!this.selectedId) return this.showMissingFields(['selectedRecord']);
    this.perform(
      this.api.post(`/scheduling/appointments/${encodeURIComponent(this.selectedId)}/cancel`, {
        reason: this.appointmentCancelReason || this.t('customerCancellation'),
      }),
    );
  }

  loadVehicleRecord(vehicleId = this.vehicleId): void {
    if (!vehicleId) {
      this.vehicleRecord.set(null);
      return;
    }
    this.api.get<unknown>(`/vehicles/${encodeURIComponent(vehicleId)}/record`).subscribe({
      next: (data) => this.vehicleRecord.set(isRecord(data) ? data : null),
      error: (error: HttpErrorResponse) => this.error.set(this.errorMessage(error)),
    });
  }

  saveTechnicalNote(): void {
    if (!this.vehicleId || !this.noteText.trim()) {
      return this.showMissingFields([
        ...(!this.vehicleId ? ['chooseVehicle' as TranslationKey] : []),
        ...(!this.noteText.trim() ? ['note' as TranslationKey] : []),
      ]);
    }
    this.perform(this.api.post(`/vehicles/${encodeURIComponent(this.vehicleId)}/notes`, {
      diagnosis: this.noteText.trim(),
    }));
  }

  createInternalUser(): void {
    if (!this.internalUserName.trim() || !this.internalUserEmail.trim() || this.internalUserPassword.length < 10) {
      return this.showRequired(this.t('completeUserFields'));
    }
    this.perform(this.api.post('/users', {
      full_name: this.internalUserName.trim(),
      email: this.internalUserEmail.trim(),
      role: this.internalUserRole,
      temporary_password: this.internalUserPassword,
    }), false, undefined, undefined, 'recordCreated');
  }

  isCrudPage(): boolean {
    return this.page() === 'customers'
      || (this.page() === 'vehicles' && this.isAdminVehicleManagementPage())
      || this.page() === 'catalog'
      || this.page() === 'users'
      || (this.page() === 'inventory' && this.session.user()?.role === 'ADMIN');
  }

  isAdminVehicleManagementPage(): boolean {
    return this.router.url.includes('/admin/vehiculos');
  }

  recordActive(id: string): boolean {
    return this.managementRecords().find((record) => record.id === id)?.['active'] !== false;
  }

  editRecord(id: string): void {
    const record = this.managementRecords().find((item) => item.id === id);
    if (!record) return this.showMissingFields(['selectedRecord']);
    this.editFieldErrors.set({});
    this.editingRecord.set(record);
    this.editForm = {
      ...emptyManagementForm(),
      full_name: String(record['full_name'] ?? ''),
      document_type: String(record['document_type'] ?? 'CC'),
      document_number: String(record['document_number'] ?? ''),
      phone: String(record['phone'] ?? ''),
      email: String(record['email'] ?? ''),
      customer_id: String(record['customer_id'] ?? ''),
      serial_number: String(record['serial_number'] ?? ''),
      plate: String(record['plate'] ?? ''),
      brand: String(record['brand'] ?? ''),
      model: String(record['model'] ?? ''),
      year: this.optionalNumber(record['year']),
      battery_capacity_ah: this.optionalNumber(record['battery_capacity_ah']),
      cell_type: String(record['cell_type'] ?? ''),
      motor_power_w: this.optionalNumber(record['motor_power_w']),
      controller: String(record['controller'] ?? ''),
      code: String(record['code'] ?? ''),
      name: String(record['name'] ?? ''),
      description: String(record['description'] ?? ''),
      price: this.numericValue(record['price']),
      duration_minutes: this.numericValue(record['duration_minutes']) || 30,
      sku: String(record['sku'] ?? ''),
      category: String(record['category'] ?? ''),
      voltage: String(record['voltage'] ?? ''),
      unit_price: this.numericValue(record['unit_price']),
      min_threshold: this.numericValue(record['min_threshold']),
      role: String(record['role'] ?? 'MECHANIC'),
      active: record['active'] !== false,
    };
    queueMicrotask(() => this.editRecordHeading?.nativeElement.focus());
  }

  saveRecord(): void {
    this.editFieldErrors.set({});
    this.error.set('');
    const record = this.editingRecord();
    if (!record?.id) return this.showMissingFields(['selectedRecord']);
    let path = '';
    let payload: Record<string, unknown> = {};
    if (this.page() === 'customers') {
      path = `/customers/${encodeURIComponent(record.id)}`;
      payload = {
        full_name: this.editForm.full_name.trim(),
        document_type: this.editForm.document_type,
        document_number: this.editForm.document_number.trim(),
        phone: this.editForm.phone.trim(),
        email: this.editForm.email.trim() || null,
      };
    } else if (this.page() === 'vehicles') {
      path = `/vehicles/${encodeURIComponent(record.id)}`;
      payload = {
        customer_id: this.editForm.customer_id,
        serial_number: this.editForm.serial_number.trim(),
        plate: this.editForm.plate.trim() || null,
        brand: this.editForm.brand.trim(),
        model: this.editForm.model.trim(),
        year: this.editForm.year,
        battery_capacity_ah: this.editForm.battery_capacity_ah,
        cell_type: this.editForm.cell_type.trim() || null,
        motor_power_w: this.editForm.motor_power_w,
        controller: this.editForm.controller.trim() || null,
      };
    } else if (this.page() === 'catalog') {
      path = `/catalog/services/${encodeURIComponent(record.id)}`;
      payload = {
        code: this.editForm.code.trim(),
        name: this.editForm.name.trim(),
        description: this.editForm.description.trim(),
        price: this.editForm.price,
        duration_minutes: this.editForm.duration_minutes,
        active: this.editForm.active,
      };
    } else if (this.page() === 'inventory') {
      path = `/inventory/parts/${encodeURIComponent(record.id)}`;
      payload = {
        sku: this.editForm.sku.trim(),
        name: this.editForm.name.trim(),
        category: this.editForm.category.trim() || 'General',
        voltage: this.editForm.voltage.trim() || null,
        unit_price: this.editForm.unit_price,
        min_threshold: this.editForm.min_threshold,
        active: this.editForm.active,
      };
    } else {
      path = `/users/${encodeURIComponent(record.id)}`;
      payload = {
        full_name: this.editForm.full_name.trim(),
        email: this.editForm.email.trim(),
        role: this.editForm.role,
        active: this.editForm.active,
      };
    }
    this.perform(this.api.patch(path, payload), false, () => {
      this.editingRecord.set(null);
      this.editForm = emptyManagementForm();
      this.focusRecordsHeading();
    }, (error) => {
      const fieldErrors: Record<string, string> = {};
      const details = error.error?.detail;
      if (Array.isArray(details)) {
        for (const detail of details) {
          if (!isRecord(detail) || typeof detail['msg'] !== 'string' || !Array.isArray(detail['loc'])) continue;
          const location = detail['loc'];
          const field = location[0] === 'body' ? location[1] : undefined;
          if (typeof field === 'string' && field in this.editForm) fieldErrors[field] = detail['msg'];
        }
      }
      this.editFieldErrors.set(fieldErrors);
      this.error.set(this.errorMessage(error));
    }, 'recordUpdated');
  }

  cancelEdit(): void {
    this.editFieldErrors.set({});
    this.editingRecord.set(null);
    this.editForm = emptyManagementForm();
    this.focusRecordsHeading();
  }

  clearEditFieldError(field: string): void {
    this.editFieldErrors.update((errors) => {
      if (!(field in errors)) return errors;
      const updated = { ...errors };
      delete updated[field];
      return updated;
    });
  }

  deleteRecord(id: string): void {
    const record = this.managementRecords().find((item) => item.id === id);
    if (!record) return this.showMissingFields(['selectedRecord']);
    if (!window.confirm(this.t('confirmDeleteRecord'))) return;
    const path = this.page() === 'customers'
      ? `/customers/${encodeURIComponent(id)}`
      : `/vehicles/${encodeURIComponent(id)}`;
    this.perform(this.api.delete(path), false, () => {
      if (this.editingRecord()?.id === id) this.cancelEdit();
      this.focusRecordsHeading();
    }, undefined, 'recordDeleted');
  }

  toggleRecordActive(id: string): void {
    const record = this.managementRecords().find((item) => item.id === id);
    if (!record) return this.showMissingFields(['selectedRecord']);
    const active = record['active'] !== false;
    let request: import('rxjs').Observable<unknown>;
    if (this.page() === 'catalog') {
      request = active
        ? this.api.post(`/catalog/services/${encodeURIComponent(id)}/deactivate`, {})
        : this.api.patch(`/catalog/services/${encodeURIComponent(id)}`, { active: true });
    } else if (this.page() === 'inventory') {
      request = active
        ? this.api.post(`/inventory/parts/${encodeURIComponent(id)}/deactivate`, {})
        : this.api.patch(`/inventory/parts/${encodeURIComponent(id)}`, { active: true });
    } else {
      request = this.api.patch(`/users/${encodeURIComponent(id)}`, { active: !active });
    }
    this.perform(request, false, () => this.focusRecordsHeading(), undefined, active ? 'recordDeactivated' : 'recordReactivated');
  }

  toggleInactiveRecords(event: Event): void {
    this.includeInactiveRecords.set((event.target as HTMLInputElement).checked);
    this.cancelEdit();
    this.load();
  }

  loadServiceParts(serviceId = this.selectedId): void {
    if (!serviceId) {
      this.servicePartRows.set([]);
      this.servicePartDraft.set([]);
      return;
    }
    this.api.get<unknown>(`/catalog/services/${encodeURIComponent(serviceId)}/parts`).subscribe({
      next: (data) => {
        this.servicePartRows.set(this.toRecords(data));
        this.servicePartDraft.set(this.toRecords(data).map((row) => ({
          part_id: String(isRecord(row['part']) ? row['part']['id'] ?? '' : ''),
          quantity: Number(row['quantity'] ?? 1),
        })).filter((row) => row.part_id));
      },
      error: (error: HttpErrorResponse) => this.error.set(this.errorMessage(error)),
    });
  }

  addServicePart(): void {
    if (!this.servicePartId) return this.showMissingFields(['choosePart']);
    const parts = this.servicePartDraft();
    const existing = parts.find((row) => row.part_id === this.servicePartId);
    if (existing) {
      this.servicePartDraft.set(parts.map((row) => row.part_id === this.servicePartId
        ? { ...row, quantity: row.quantity + this.servicePartQuantity }
        : row));
    } else {
      this.servicePartDraft.set([...parts, { part_id: this.servicePartId, quantity: this.servicePartQuantity }]);
    }
    this.servicePartId = '';
    this.servicePartQuantity = 1;
  }

  removeServicePart(partId: string): void {
    this.servicePartDraft.set(this.servicePartDraft().filter((row) => row.part_id !== partId));
  }

  saveServiceParts(): void {
    if (!this.selectedId) return this.showMissingFields(['selectedRecord']);
    this.perform(
      this.api.put(`/catalog/services/${encodeURIComponent(this.selectedId)}/parts`, this.servicePartDraft()),
      false,
      (response) => {
        if (
          isRecord(response)
          && typeof response['preserved_appointment_reservations'] === 'number'
          && response['preserved_appointment_reservations'] > 0
        ) {
          this.message.set(
            `${response['preserved_appointment_reservations']} ${this.t('preservedAppointmentReservations')}`,
          );
        }
      },
    );
  }

  createService(): void {
    const missing = [
      !this.serviceCode && 'serviceCode',
      !this.serviceName && 'service',
      this.servicePrice <= 0 && 'price',
      this.serviceDuration <= 0 && 'duration',
    ].filter((field): field is TranslationKey => Boolean(field));
    if (missing.length) return this.showMissingFields(missing);
    this.perform(
      this.api.post('/catalog/services', {
        code: this.serviceCode,
        name: this.serviceName,
        description: this.serviceDescription,
        price: this.servicePrice,
        duration_minutes: this.serviceDuration,
      }),
      false,
      undefined,
      undefined,
      'recordCreated',
    );
  }

  trackOrder(): void {
    if (!this.trackingCode) return this.showMissingFields(['trackingCode']);
    this.router.navigate(['/seguimiento', this.trackingCode]);
  }

  isCustomerRegistrationPage(): boolean {
    return this.router.url.includes('/recepcion/clientes/nuevo');
  }

  isWalkInPage(): boolean {
    return this.router.url.includes('/recepcion/ingreso');
  }

  clearWorkOrderFaultTypeError(): void {
    this.workOrderFaultTypeError.set(false);
    if (this.error() === this.t('faultTypeRequired')) this.error.set('');
  }

  onServiceChange(): void {
    this.slotId = '';
    this.loadAvailableSlots();
  }

  onSelectedRecordChange(): void {
    if (this.page() === 'workOrders' && this.session.user()?.role === 'MECHANIC') {
      this.loadOrderDetails();
    }
    if (this.page() === 'catalog') {
      this.loadServiceParts();
    }
  }

  selectedWorkOrderStatus(): string {
    return this.rows().find((row) => row.id === this.selectedId)?.status ?? '';
  }

  workOrderParts(): ApiRecord[] {
    const parts = this.workOrderDetail()?.['parts'];
    return this.toRecords(parts);
  }

  workOrderServices(): ApiRecord[] {
    const services = this.workOrderDetail()?.['services'];
    return this.toRecords(services);
  }

  technicalNotes(): ApiRecord[] {
    return this.toRecords(this.vehicleRecord()?.['notes']);
  }

  vehicleWorkOrders(): ApiRecord[] {
    return this.toRecords(this.vehicleRecord()?.['work_orders']);
  }

  partDisplayName(partId: string): string {
    return String(this.parts().find((part) => part.id === partId)?.name ?? partId);
  }

  recordId(value: unknown): string {
    return typeof value === 'string' ? value : '';
  }

  displayStatus(value: unknown): string {
    if (typeof value !== 'string') return this.displayValue(value);
    const keys: Record<string, TranslationKey> = {
      RECEIVED: 'statusReceived',
      ASSIGNED: 'statusAssigned',
      DIAGNOSING: 'statusDiagnosing',
      REPAIRING: 'statusRepairing',
      WAITING_PARTS: 'statusWaitingParts',
      PENDING_INSTALLATION: 'statusPendingInstallation',
      FINISHED: 'statusFinished',
      DELIVERED: 'statusDelivered',
      CANCELLED: 'statusCancelled',
      CONFIRMED: 'statusConfirmed',
      HELD: 'statusHeld',
      NO_SHOW: 'statusNoShow',
      RESCHEDULED: 'statusRescheduled',
    };
    return keys[value] ? this.t(keys[value]) : this.displayValue(value);
  }

  formatCurrency(value: unknown): string {
    const amount = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(amount)) return String(value ?? '');
    return new Intl.NumberFormat('es-CO', {
      style: 'currency',
      currency: 'COP',
      maximumFractionDigits: 0,
    }).format(amount);
  }

  trackingTimeline(status: unknown): string[] {
    const states = [
      'statusReceived',
      'statusAssigned',
      'statusDiagnosing',
      'statusRepairing',
      'statusFinished',
      'statusDelivered',
    ] as const;
    const actualStates: Record<string, (typeof states)[number]> = {
      RECEIVED: 'statusReceived',
      ASSIGNED: 'statusAssigned',
      DIAGNOSING: 'statusDiagnosing',
      REPAIRING: 'statusRepairing',
      WAITING_PARTS: 'statusRepairing',
      PENDING_INSTALLATION: 'statusRepairing',
      FINISHED: 'statusFinished',
      DELIVERED: 'statusDelivered',
    };
    const currentIndex = states.indexOf(actualStates[String(status)] ?? 'statusReceived');
    return states.map((key, index) => `${index <= currentIndex ? '✓ ' : '○ '}${this.t(key)}`);
  }

  formatHoldCountdown(): string {
    const seconds = this.holdRemainingSeconds();
    if (seconds === null) return '';
    return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
  }

  changePassword(): void {
    if (!this.currentPassword) return this.showRequired(this.t('currentPassword'));
    if (this.newPassword.length < 10) return this.showRequired(this.t('passwordMinimum'));
    this.perform(
      this.api.post('/auth/change-password', {
        current_password: this.currentPassword,
        new_password: this.newPassword,
      }),
      true,
    );
  }

  private perform(
    request: import('rxjs').Observable<unknown>,
    passwordChange = false,
    onSuccess?: (response: unknown) => void,
    onError?: (error: HttpErrorResponse) => void,
    successMessage: TranslationKey = 'saved',
  ): void {
    this.error.set('');
    this.message.set('');
    this.saving.set(true);
    request.subscribe({
      next: (response) => {
        this.saving.set(false);
        if (passwordChange) this.session.completePasswordChange();
        if (isRecord(response) && typeof response['id'] === 'string') {
          this.selectedId = response['id'];
        }
        if (this.page() === 'appointments') {
          if (isRecord(response) && response['status'] === 'HELD') {
            this.startHoldCountdown(response['expires_at']);
            if (this.isCustomerBookingPage()) {
              this.bookingStep.set(1);
              this.vehicleId = '';
              this.serviceId = '';
              this.slotId = '';
            }
          } else {
            this.stopHoldCountdown();
          }
        }
        const trackingCode = isRecord(response) && typeof response['tracking_code'] === 'string'
          ? response['tracking_code']
          : '';
        this.message.set(trackingCode
          ? `${this.t('saved')} ${this.t('trackingCode')}: ${trackingCode}`
          : passwordChange ? this.t('passwordSaved') : this.t(successMessage));
        onSuccess?.(response);
        this.load(true);
        if (this.page() === 'workOrders' && this.session.user()?.role === 'MECHANIC' && this.selectedId) {
          this.loadOrderDetails();
        }
      },
      error: (error: HttpErrorResponse) => {
        this.saving.set(false);
        onError?.(error);
        this.error.set(this.errorMessage(error));
      },
    });
  }

  private focusRecordsHeading(): void {
    queueMicrotask(() => this.recordsHeading?.nativeElement.focus());
  }

  private updatePage(): void {
    const url = this.router.url;
    const dataPage = this.route.snapshot.data['page'] as string | undefined;
    const selected = dataPage ?? this.pageForUrl(url);
    this.page.set(selected);
    if (selected === 'appointments' && this.isCustomerBookingPage()) this.bookingStep.set(1);
    let titleKey = pageTitles[selected] ?? 'pageDashboard';
    const role = this.session.user()?.role;
    if (selected === 'appointments') {
      titleKey = role === 'CUSTOMER'
        ? this.router.url.includes('/reprogramar')
          ? 'appointmentReschedule'
          : this.isCustomerBookingPage() ? 'createAppointment' : 'customerAppointments'
        : 'appointments';
    } else if (selected === 'vehicles') {
      titleKey = this.isAdminVehicleManagementPage()
        ? 'pageVehicles'
        : this.isCustomerRegistrationPage()
        ? 'registerCustomer'
        : role === 'CUSTOMER' && !this.isCustomerHistoryPage() ? 'customerVehicles' : 'vehicleRecord';
    } else if (selected === 'workOrders') {
      titleKey = this.isPaymentPage()
        ? 'paymentAndDelivery'
        : role === 'ADMIN'
        ? 'mechanicAssignment'
        : role === 'MECHANIC'
          ? this.router.url.includes('/taller/ordenes/') ? 'workOrderDetail' : 'bay'
          : this.isPaymentPage() ? 'paymentAndDelivery' : this.isWalkInPage() ? 'createWalkIn' : 'createOrder';
    } else if (selected === 'reports' && this.isAuditPage()) {
      titleKey = 'reports';
    }
    this.titleKey.set(titleKey);
  }

  private loadOptions(page: string, role?: string): void {
    if (page === 'appointments' || page === 'workOrders' || page === 'vehicles') {
      const vehiclePath = role === 'CUSTOMER' ? '/vehicles/mine' : '/vehicles';
      this.api.get<unknown>(vehiclePath).subscribe({
        next: (data) => this.vehicles.set(this.toRecords(data)),
        error: (error: HttpErrorResponse) => {
          this.vehicles.set([]);
          this.error.set(this.errorMessage(error));
        },
      });
    }
    if (page === 'appointments') {
      this.api.get<unknown>('/catalog/services').subscribe({
        next: (data) => this.services.set(this.toRecords(data)),
        error: (error: HttpErrorResponse) => {
          this.services.set([]);
          this.error.set(this.errorMessage(error));
        },
      });
      this.loadAvailableSlots();
    }
    if (page === 'inventory' || page === 'workOrders' || page === 'catalog') {
      this.api.get<unknown>('/inventory/parts').subscribe({
        next: (data) => this.parts.set(this.toRecords(data)),
        error: (error: HttpErrorResponse) => {
          this.parts.set([]);
          this.error.set(this.errorMessage(error));
        },
      });
    }
    if (page === 'vehicles' && role !== 'CUSTOMER') {
      this.api.get<unknown>('/customers').subscribe({
        next: (data) => this.customers.set(this.toRecords(data)),
        error: (error: HttpErrorResponse) => {
          this.customers.set([]);
          this.error.set(this.errorMessage(error));
        },
      });
    }
    if (page === 'workOrders' && role === 'ADMIN') {
      this.api.get<unknown>('/users?role=MECHANIC&active=true').subscribe({
        next: (data) => this.mechanics.set(this.toRecords(data)),
        error: (error: HttpErrorResponse) => {
          this.mechanics.set([]);
          this.error.set(this.errorMessage(error));
        },
      });
    }
    if (page === 'workOrders' && (role === 'MECHANIC' || role === 'RECEPTIONIST' || role === 'ADMIN')) {
      this.api.get<unknown>('/catalog/services').subscribe({
        next: (data) => this.services.set(this.toRecords(data)),
        error: (error: HttpErrorResponse) => {
          this.services.set([]);
          this.error.set(this.errorMessage(error));
        },
      });
    }
  }

  private loadAvailableSlots(): void {
    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const serviceQuery = this.serviceId ? `&service_id=${encodeURIComponent(this.serviceId)}` : '';
    this.api.get<unknown>(`/scheduling/availability?from=${tomorrow}${serviceQuery}`).subscribe({
      next: (data) => this.slots.set(this.toRecords(data)
        .filter((slot) => Number(slot['available'] ?? 0) > 0 && !slot['blocked'])),
      error: (error: HttpErrorResponse) => {
        this.slots.set([]);
        this.error.set(this.errorMessage(error));
      },
    });
  }

  private openTrackingStream(code: string): void {
    if (!code || code === 'demo') return;
    this.trackingStream?.close();
    this.trackingStream = new EventSource(`/api/v1/tracking/${encodeURIComponent(code)}/events`);
    this.trackingStream.addEventListener('work_order.updated', (event: Event) => {
      if (!(event instanceof MessageEvent) || typeof event.data !== 'string') return;
      try {
        const data: unknown = JSON.parse(event.data);
        if (!isRecord(data)) return;
        this.trackingState.set(data);
        this.rows.set(this.toRows(data));
        this.trackingLive.set(true);
      } catch {
        this.trackingStream?.close();
        this.trackingLive.set(false);
        this.error.set(this.t('trackingUpdateError'));
      }
    });
    this.trackingStream.onerror = () => this.trackingLive.set(false);
  }

  private reportSummaryPath(): string {
    const to = new Date();
    const from = new Date(to);
    from.setDate(from.getDate() - 6);
    const formatDate = (date: Date) => [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, '0'),
      String(date.getDate()).padStart(2, '0'),
    ].join('-');
    return `/reports/summary?from=${formatDate(from)}&to=${formatDate(to)}`;
  }

  private reportNumber(field: string): number {
    const value = Number(this.reportRow(field)?.secondary ?? 0);
    return Number.isFinite(value) ? value : 0;
  }

  private numericValue(value: unknown): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  private optionalNumber(value: unknown): number | null {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  private availablePartStock(part: ApiRecord): number {
    if (part['available_stock'] !== undefined) return this.numericValue(part['available_stock']);
    return Math.max(0, this.numericValue(part['physical_stock']) - this.numericValue(part['reserved_stock']));
  }

  private roundHalfEven(numerator: number, denominator: number): number {
    const quotient = Math.floor(numerator / denominator);
    const remainder = numerator % denominator;
    if (remainder * 2 > denominator) return quotient + 1;
    if (remainder * 2 < denominator) return quotient;
    return quotient % 2 === 0 ? quotient : quotient + 1;
  }

  private reportRow(field: string): DisplayRow | undefined {
    const normalizedField = field.replace(/[\s_]+/g, '').toLowerCase();
    return this.rows().find((row) => row.primary.replace(/[\s_]+/g, '').toLowerCase() === normalizedField);
  }

  private startHoldCountdown(expiresAt: unknown): void {
    this.stopHoldCountdown();
    if (typeof expiresAt !== 'string') return;
    const expiry = Date.parse(expiresAt);
    if (Number.isNaN(expiry)) {
      this.error.set(this.t('holdTimerError'));
      return;
    }
    const update = () => {
      const remaining = Math.max(0, Math.ceil((expiry - Date.now()) / 1000));
      this.holdRemainingSeconds.set(remaining);
      if (remaining === 0) this.stopHoldCountdown(false);
    };
    update();
    if (this.holdRemainingSeconds() !== 0) {
      this.holdCountdown = setInterval(update, 1000);
    }
  }

  private stopHoldCountdown(clearValue = true): void {
    if (this.holdCountdown) clearInterval(this.holdCountdown);
    this.holdCountdown = undefined;
    if (clearValue) this.holdRemainingSeconds.set(null);
  }

  private toRecords(data: unknown): ApiRecord[] {
    return Array.isArray(data) ? data.filter(isRecord) : [];
  }

  private pageForUrl(url: string): string {
    if (url.includes('/admin/clientes')) return 'customers';
    if (url.includes('seguimiento')) return 'tracking';
    if (url.includes('agendar') || url.includes('citas') || url.includes('agenda')) return 'appointments';
    if (url.includes('vehiculo') || url.includes('expediente')) return 'vehicles';
    if (url.includes('inventario')) return 'inventory';
    if (url.includes('catalogo')) return 'catalog';
    if (url.includes('indicadores') || url.includes('bitacora')) return 'reports';
    if (url.includes('usuarios')) return 'users';
    if (url.includes('bahia') || url.includes('ordenes') || url.includes('asignacion')) return 'workOrders';
    return 'dashboard';
  }

  private toRows(data: unknown): DisplayRow[] {
    if (isRecord(data) && this.page() === 'tracking') {
      return [{
        id: String(data['order_number'] ?? 'tracking'),
        primary: String(data['order_number'] ?? ''),
        secondary: this.displayValue(data['vehicle']),
        status: String(data['status'] ?? ''),
      }];
    }
    if (!Array.isArray(data)) {
      if (!isRecord(data)) return [];
      return Object.entries(data).map(([key, value]) => ({
        id: key,
        primary: this.formatLabel(key),
        secondary: this.displayValue(value) || this.t('notAvailable'),
        status: this.t('notApplicable'),
      }));
    }
    return data.filter(isRecord).map((record, index) => {
      const primaryFields = this.page() === 'catalog'
        ? ['name', 'code', 'number', 'full_name', 'serial_number', 'sku', 'receipt_number', 'email']
        : ['number', 'code', 'name', 'full_name', 'serial_number', 'sku', 'receipt_number', 'email'];
      const primary = this.firstDisplayValue(record, primaryFields) || this.t('notAvailable');
      const secondary = this.joinDisplayValues(record, [
        'code', 'model', 'start_time', 'description', 'fault_description', 'diagnosis',
        'available_stock', 'queue_position', 'email', 'created_at', 'document_number',
        'brand', 'price', 'duration_minutes', 'expires_at',
      ]);
      const statusValue = record['status'] ?? record['active'];
      return {
        id: String(record['id'] ?? record['code'] ?? `${index}`),
        primary,
        secondary,
        status: statusValue === undefined || statusValue === null
          ? this.t('notAvailable')
          : this.displayStatus(statusValue),
        version: typeof record['version'] === 'number' ? record['version'] : undefined,
      };
    });
  }

  private firstDisplayValue(record: ApiRecord, keys: string[]): string {
    for (const key of keys) {
      const value = this.displayValue(record[key]);
      if (value) return value;
    }
    return '';
  }

  private joinDisplayValues(record: ApiRecord, keys: string[]): string {
    return keys
      .map((key) => this.displayValue(record[key]))
      .filter(Boolean)
      .join(' · ');
  }

  displayValue(value: unknown): string {
    if (value === null || value === undefined) return '';
    if (typeof value === 'boolean') return this.t(value ? 'active' : 'inactive');
    if (typeof value === 'string') return value.replaceAll('_', ' ');
    if (typeof value === 'number') return String(value);
    if (Array.isArray(value)) return value.map((item) => this.displayValue(item)).filter(Boolean).join(', ');
    if (isRecord(value)) {
      const entries = Object.entries(value)
        .map(([key, item]) => `${this.formatLabel(key)}: ${this.displayValue(item)}`)
        .filter((item) => !item.endsWith(': '))
        .join(' · ');
      return entries || this.t('notAvailable');
    }
    return '';
  }

  private formatLabel(value: string): string {
    return value.replaceAll('_', ' ');
  }

  private showRequired(message = this.t('required')): void {
    this.error.set(message);
  }

  private showMissingFields(fields: TranslationKey[]): void {
    this.showRequired(fields.map((field) => this.t(field)).join(' · '));
  }

  private errorMessage(error: HttpErrorResponse): string {
    const detail = error.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg ?? '').filter(Boolean).join(' ');
    return this.t('loadError');
  }
}
