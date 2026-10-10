import type { APIRequestContext, APIResponse } from '@playwright/test';
import type { LoginResponse, OrderInput, ProductInput } from './types';
import { redact } from '../utils/redact';

export interface Exchange {
  method: string;
  url: string;
  requestHeaders: Record<string, string>;
  requestBody: unknown;
  status: number;
  responseHeaders: Record<string, string>;
  responseBody: unknown;
  durationMs: number;
}

export interface OrderOptions {
  idempotencyKey?: string;
  /** Opt-in fault injection point (requires ENABLE_TEST_HOOKS on the server). */
  fault?: 'after_inventory_decrement' | 'after_order_insert';
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH';

/**
 * Thin, typed wrapper over Playwright's APIRequestContext.
 *
 * - Returns the raw APIResponse: tests assert status, headers and body themselves.
 * - Records every exchange (redacted) so a failing test can attach the full HTTP conversation.
 */
export class ApiClient {
  constructor(
    private readonly request: APIRequestContext,
    private readonly token?: string,
    /** Shared by every client derived via `as()`, so diagnostics show the whole conversation. */
    readonly exchanges: Exchange[] = [],
  ) {}

  /** A client for the same request context and exchange log, authenticated with `token`. */
  as(token: string | undefined): ApiClient {
    return new ApiClient(this.request, token, this.exchanges);
  }

  get authToken(): string | undefined {
    return this.token;
  }

  // --- auth -------------------------------------------------------------------------------
  login(email: string, password: string): Promise<APIResponse> {
    return this.send('POST', '/api/v1/auth/login', { email, password });
  }

  async loginAs(email: string, password: string): Promise<ApiClient> {
    const response = await this.login(email, password);
    if (response.status() !== 200) {
      throw new Error(`Login for ${email} failed: HTTP ${response.status()} ${await response.text()}`);
    }
    const body = (await response.json()) as LoginResponse;
    return this.as(body.access_token);
  }

  logout(): Promise<APIResponse> {
    return this.send('POST', '/api/v1/auth/logout');
  }

  me(): Promise<APIResponse> {
    return this.send('GET', '/api/v1/auth/me');
  }

  createUser(body: Record<string, unknown>): Promise<APIResponse> {
    return this.send('POST', '/api/v1/users', body);
  }

  // --- products ---------------------------------------------------------------------------
  listProducts(params: Record<string, string | number | boolean> = {}): Promise<APIResponse> {
    return this.send('GET', '/api/v1/products', undefined, { params });
  }

  getProduct(id: number | string): Promise<APIResponse> {
    return this.send('GET', `/api/v1/products/${id}`);
  }

  getInventory(id: number | string): Promise<APIResponse> {
    return this.send('GET', `/api/v1/products/${id}/inventory`);
  }

  createProduct(body: ProductInput | Record<string, unknown>): Promise<APIResponse> {
    return this.send('POST', '/api/v1/products', body);
  }

  updateProduct(id: number, body: Record<string, unknown>): Promise<APIResponse> {
    return this.send('PATCH', `/api/v1/products/${id}`, body);
  }

  setInventory(id: number, available: unknown): Promise<APIResponse> {
    return this.send('PUT', `/api/v1/products/${id}/inventory`, { available });
  }

  // --- orders -----------------------------------------------------------------------------
  createOrder(body: OrderInput | unknown, options: OrderOptions = {}): Promise<APIResponse> {
    const headers: Record<string, string> = {};
    if (options.idempotencyKey !== undefined) headers['Idempotency-Key'] = options.idempotencyKey;
    if (options.fault) headers['X-Test-Fault'] = options.fault;
    return this.send('POST', '/api/v1/orders', body, { headers });
  }

  getOrder(id: string): Promise<APIResponse> {
    return this.send('GET', `/api/v1/orders/${id}`);
  }

  listOrders(params: Record<string, number> = {}): Promise<APIResponse> {
    return this.send('GET', '/api/v1/orders', undefined, { params });
  }

  cancelOrder(id: string): Promise<APIResponse> {
    return this.send('POST', `/api/v1/orders/${id}/cancel`);
  }

  // --- generic ----------------------------------------------------------------------------
  /** Escape hatch for negative tests (raw bodies, custom headers, unusual methods). */
  async send(
    method: Method,
    url: string,
    data?: unknown,
    options: { headers?: Record<string, string>; params?: Record<string, string | number | boolean> } = {},
  ): Promise<APIResponse> {
    const headers: Record<string, string> = { ...options.headers };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    const started = Date.now();
    const response = await this.request.fetch(url, {
      method,
      headers,
      params: options.params,
      data,
    });
    await this.record(method, response, headers, data, Date.now() - started);
    return response;
  }

  private async record(
    method: string,
    response: APIResponse,
    requestHeaders: Record<string, string>,
    requestBody: unknown,
    durationMs: number,
  ): Promise<void> {
    let responseBody: unknown;
    try {
      responseBody = await response.json();
    } catch {
      responseBody = (await response.text()).slice(0, 2_000);
    }
    this.exchanges.push({
      method,
      url: response.url(),
      requestHeaders: redact(requestHeaders) as Record<string, string>,
      requestBody: redact(requestBody),
      status: response.status(),
      responseHeaders: redact(response.headers()) as Record<string, string>,
      responseBody: redact(responseBody),
      durationMs,
    });
  }
}
