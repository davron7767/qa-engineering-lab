import { randomBytes } from 'node:crypto';
import type { ProductInput } from '../clients/types';

/**
 * Unique, collision-resistant identifiers so parallel workers and repeated runs never share
 * records. The run id keeps data from one run recognisable when debugging a shared database.
 */
const runId = Date.now().toString(36).toUpperCase();

export function uniqueSuffix(): string {
  return `${runId}-${randomBytes(3).toString('hex').toUpperCase()}`;
}

export function uniqueSku(prefix = 'PW'): string {
  return `${prefix}-${uniqueSuffix()}`.slice(0, 32);
}

export function uniqueEmail(): string {
  return `pw-${uniqueSuffix().toLowerCase()}@qa-commerce.test`;
}

export function uniqueIdempotencyKey(): string {
  return `pw-${uniqueSuffix()}`;
}

export function productInput(overrides: Partial<ProductInput> = {}): ProductInput {
  const sku = overrides.sku ?? uniqueSku();
  return {
    sku,
    name: `Test Product ${sku}`,
    description: 'Created by the Playwright suite',
    price: '10.00',
    inventory: 10,
    is_active: true,
    ...overrides,
  };
}

/** Synthetic test-only password; meets the 12-character minimum. */
export const TEST_USER_PASSWORD = 'Playwright#Local1';
