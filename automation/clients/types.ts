/** TypeScript view of the QA Commerce API contract (see docs/api-contract.md). */

export type Money = string; // "19.99" - always two decimal places

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: 'customer' | 'admin';
  customer_ref: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  user: User;
}

export interface Product {
  id: number;
  sku: string;
  name: string;
  description: string;
  price: Money;
  inventory: number;
  is_active: boolean;
  in_stock: boolean;
  created_at: string;
  updated_at: string;
}

export interface Inventory {
  product_id: number;
  sku: string;
  available: number;
  in_stock: boolean;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface OrderItem {
  product_id: number;
  sku: string;
  product_name: string;
  quantity: number;
  unit_price: Money;
  line_total: Money;
}

export interface Order {
  id: string;
  customer_ref: string;
  status: 'confirmed' | 'cancelled';
  currency: 'USD';
  items: OrderItem[];
  total: Money;
  created_at: string;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details: Array<Record<string, unknown>>;
    request_id: string | null;
  };
}

export interface ProductInput {
  sku: string;
  name: string;
  description?: string;
  price: string | number;
  inventory: number;
  is_active?: boolean;
}

/** Deliberately loose: negative tests send malformed bodies on purpose. */
export type OrderInput = { items: unknown } & Record<string, unknown>;
