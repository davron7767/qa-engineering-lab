import { test as base, type APIResponse, type Page } from '@playwright/test';
import { ApiClient } from '../clients/api-client';
import type { Product, ProductInput, User } from '../clients/types';
import { productInput, TEST_USER_PASSWORD, uniqueEmail } from '../data/factories';
import { db } from '../utils/db';
import { env } from '../utils/env';
import { expect } from './matchers';

export interface TestCustomer {
  user: User;
  email: string;
  password: string;
  token: string;
  api: ApiClient;
}

export interface TestData {
  /** Create an isolated product (unique SKU) via the admin API. Deactivated after the test. */
  createProduct(overrides?: Partial<ProductInput>): Promise<Product>;
  /** Create an isolated customer account via the admin API. */
  createCustomer(): Promise<TestCustomer>;
}

interface TestFixtures {
  /** Anonymous API client; every exchange made through it (or derived clients) is logged. */
  api: ApiClient;
  /** API client authenticated as the seeded admin. */
  adminApi: ApiClient;
  testData: TestData;
  /** A brand-new customer per test, so order history and idempotency keys are isolated. */
  customer: TestCustomer;
  /** Browser page already signed in as `customer` (session cookie injected - no UI login). */
  customerPage: Page;
}

interface WorkerFixtures {
  adminToken: string;
  dbConnection: void;
}

export const test = base.extend<TestFixtures, WorkerFixtures>({
  // One admin session per worker keeps the suite fast and avoids a login per test.
  // Login and logout each use a short-lived request context: a context held open for the whole
  // worker would reuse a keep-alive socket the server may already be closing, which surfaced as
  // an intermittent ECONNRESET on logout behind Docker Desktop's port forwarding.
  adminToken: [
    async ({ playwright }, use) => {
      const withContext = async <T>(fn: (api: ApiClient) => Promise<T>): Promise<T> => {
        const context = await playwright.request.newContext({ baseURL: env.baseUrl });
        try {
          return await fn(new ApiClient(context));
        } finally {
          await context.dispose();
        }
      };
      const token = await withContext(
        async (api) => (await api.loginAs(env.adminEmail, env.adminPassword)).authToken as string,
      );
      await use(token);
      await withContext((api) => api.as(token).logout());
    },
    { scope: 'worker' },
  ],

  dbConnection: [
    async ({}, use) => {
      await use();
      await db.close();
    },
    { scope: 'worker', auto: true },
  ],

  api: async ({ request }, use, testInfo) => {
    const client = new ApiClient(request);
    await use(client);
    // On failure, attach the whole (redacted) HTTP conversation to the report.
    if (testInfo.status !== testInfo.expectedStatus && client.exchanges.length > 0) {
      await testInfo.attach('api-exchanges.json', {
        body: JSON.stringify(client.exchanges, null, 2),
        contentType: 'application/json',
      });
    }
  },

  adminApi: async ({ api, adminToken }, use) => {
    await use(api.as(adminToken));
  },

  testData: async ({ adminApi }, use) => {
    const createdProductIds: number[] = [];
    const data: TestData = {
      async createProduct(overrides = {}) {
        const response = await adminApi.createProduct(productInput(overrides));
        await expect(response, 'test data setup: create product').toHaveStatus(201);
        const product = (await response.json()) as Product;
        createdProductIds.push(product.id);
        return product;
      },
      async createCustomer() {
        const email = uniqueEmail();
        const response = await adminApi.createUser({
          email,
          full_name: 'Playwright Customer',
          password: TEST_USER_PASSWORD,
        });
        await expect(response, 'test data setup: create customer').toHaveStatus(201);
        const user = (await response.json()) as User;
        const api = await adminApi.as(undefined).loginAs(email, TEST_USER_PASSWORD);
        return { user, email, password: TEST_USER_PASSWORD, token: api.authToken as string, api };
      },
    };
    await use(data);
    // Cleanup: products cannot be deleted (orders reference them), so retire them instead.
    for (const id of createdProductIds) {
      await adminApi.updateProduct(id, { is_active: false });
    }
  },

  customer: async ({ testData }, use) => {
    await use(await testData.createCustomer());
  },

  customerPage: async ({ page, customer }, use) => {
    await page
      .context()
      .addCookies([{ name: 'qa_session', value: customer.token, url: env.baseUrl, httpOnly: true, sameSite: 'Lax' }]);
    await use(page);
  },
});

/**
 * Typed JSON body. `response.json()` returns `any`, and Playwright intentionally hides custom
 * matchers such as toMatchSchema on `any` values, so tests read bodies through this helper.
 */
export async function json<T = Record<string, unknown>>(response: APIResponse): Promise<T> {
  return (await response.json()) as T;
}

export { expect };
