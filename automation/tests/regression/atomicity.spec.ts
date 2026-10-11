import { test, expect, json } from '../../fixtures/test';
import type { Order, Page } from '../../clients/types';
import { db } from '../../utils/db';

/**
 * Requires ENABLE_TEST_HOOKS=true on the server (the default for the local and CI stacks).
 * If hooks are disabled the server ignores X-Test-Fault, the order succeeds, and these tests
 * fail loudly rather than silently passing.
 */
test.describe('Failure after partial processing', { tag: '@regression' }, () => {
  for (const fault of ['after_inventory_decrement', 'after_order_insert'] as const) {
    test(`fault ${fault}: nothing is persisted`, async ({ customer, testData, api }) => {
      const product = await testData.createProduct({ inventory: 10 });

      const response = await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 4 }] }, { fault });

      expect(response.status(), 'server must honour X-Test-Fault (is ENABLE_TEST_HOOKS=true?)').toBe(500);
      await expect(response).toBeApiError(500, 'INJECTED_FAULT');
      // The API view...
      expect((await json<{ available: number }>(await api.getInventory(product.id))).available).toBe(10);
      expect((await json<Page<Order>>(await customer.api.listOrders())).total).toBe(0);
      // ...and the database view agree: no partial inventory update, no orphan order rows.
      expect(await db.productInventory(product.id)).toBe(10);
      expect(await db.orderCountForProduct(product.id)).toBe(0);
    });
  }

  test('500 responses do not leak internal details', async ({ customer, testData }) => {
    const product = await testData.createProduct();
    const response = await customer.api.createOrder(
      { items: [{ product_id: product.id, quantity: 1 }] },
      { fault: 'after_order_insert' },
    );
    const text = await response.text();
    expect(text).not.toContain('Traceback');
    expect(text).not.toContain('sqlalchemy');
    expect((await json<{ error: { message: string } }>(response)).error.message).toBe('An unexpected error occurred');
  });

  test('500 responses tell keep-alive clients the connection is closing', async ({ customer, testData }) => {
    const product = await testData.createProduct();
    const response = await customer.api.createOrder(
      { items: [{ product_id: product.id, quantity: 1 }] },
      { fault: 'after_order_insert' },
    );
    expect(response.status()).toBe(500);
    // Without this header, the next request on the pooled socket can fail with ECONNRESET.
    expect(response.headers()['connection'], 'unhandled errors close the connection').toBe('close');
  });
});
