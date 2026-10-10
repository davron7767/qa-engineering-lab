import type { APIResponse } from '@playwright/test';
import { test, expect, json } from '../../fixtures/test';
import type { Order } from '../../clients/types';
import { uniqueIdempotencyKey } from '../../data/factories';
import { db } from '../../utils/db';

function statuses(responses: APIResponse[]): number[] {
  return responses.map((r) => r.status()).sort();
}

/**
 * Real concurrent HTTP requests against the running server. The nightly workflow repeats these
 * (--repeat-each) to detect intermittent races rather than relying on retries.
 */
test.describe('Concurrent orders', { tag: ['@regression', '@concurrency'] }, () => {
  test('ten customers racing for the last unit: exactly one wins', async ({ testData, api }) => {
    const product = await testData.createProduct({ inventory: 1 });
    const customers = await Promise.all(Array.from({ length: 10 }, () => testData.createCustomer()));

    const responses = await Promise.all(
      customers.map((c) => c.api.createOrder({ items: [{ product_id: product.id, quantity: 1 }] })),
    );

    expect(statuses(responses)).toEqual([201, ...Array(9).fill(409)]);
    for (const r of responses.filter((r) => r.status() === 409)) {
      await expect(r).toBeApiError(409, 'INSUFFICIENT_INVENTORY');
    }
    expect((await json<{ available: number }>(await api.getInventory(product.id))).available).toBe(0);
    expect(await db.orderCountForProduct(product.id)).toBe(1);
  });

  test('concurrent partial orders never oversell', async ({ testData, customer }) => {
    const product = await testData.createProduct({ inventory: 10 });
    const responses = await Promise.all(
      Array.from({ length: 8 }, () => customer.api.createOrder({ items: [{ product_id: product.id, quantity: 3 }] })),
    );
    expect(statuses(responses)).toEqual([201, 201, 201, 409, 409, 409, 409, 409]);
    expect(await db.productInventory(product.id)).toBe(1);
  });

  test('a double-clicked submit with one Idempotency-Key creates one order', async ({ testData, customer }) => {
    const product = await testData.createProduct({ inventory: 10 });
    const key = uniqueIdempotencyKey();
    const responses = await Promise.all(
      Array.from({ length: 5 }, () =>
        customer.api.createOrder({ items: [{ product_id: product.id, quantity: 2 }] }, { idempotencyKey: key }),
      ),
    );
    expect(statuses(responses)).toEqual([200, 200, 200, 200, 201]);
    const ids = new Set(await Promise.all(responses.map(async (r) => (await json<Order>(r)).id)));
    expect(ids.size).toBe(1);
    expect(await db.productInventory(product.id)).toBe(8);
    expect(await db.ordersForCustomer(customer.user.customer_ref)).toBe(1);
  });
});
