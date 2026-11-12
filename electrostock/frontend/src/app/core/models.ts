export interface SessionUser {
  id: string;
  full_name: string;
  email: string;
  role: 'CUSTOMER' | 'RECEPTIONIST' | 'MECHANIC' | 'ADMIN';
  must_change_password?: boolean;
}

export interface LoginResponse {
  user: SessionUser;
  access_token: string;
  token_type: string;
  must_change_password: boolean;
}

export interface ApiRecord {
  id?: string;
  code?: string;
  number?: string;
  name?: string;
  full_name?: string;
  serial_number?: string;
  status?: string;
  sku?: string;
  model?: string;
  brand?: string;
  physical_stock?: number;
  available_stock?: number;
  available?: number;
  start_time?: string;
  date?: string;
  price?: number | string;
  detail?: string;
  customer_id?: string;
  document_number?: string;
  duration_minutes?: number;
  [key: string]: unknown;
}

export interface DisplayRow {
  id: string;
  primary: string;
  secondary: string;
  status: string;
  version?: number;
}
