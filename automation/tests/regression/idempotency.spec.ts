import { test, expect, json } from '../../fixtures/test';
import type { Order, Page } from '../../clients/types';
import { uniqueIdempotencyKey } from '../../data/factories';

test.describe('Duplicate submission protection', { tag: '@regression' }, () => {
  test('repeating a request with the same Idempotency-Key replays the original order', async ({
    customer,
    testData,
    api,
  }) => {
    const product = await testData.createProduct({ inventory: 10 });
    const body = { items: [{ product_id: product.id, quantity: 2 }] };
    const key = uniqueIdempotencyKey();

    const first = await customer.api.createOrder(body, { idempotencyKey: key });
    const second = await customer.api.createOrder(body, { idempotencyKey: key });

    await expect(first).toHaveStatus(201);
    await expect(second).toHaveStatus(200);
    expect(second.headers()['idempotent-replayed']).toBe('true');
    expect(await json<Order>(second)).toEqual(await json<Order>(first));
    expect((await json<{ available: number }>(await api.getInventory(product.id))).available).toBe(8);
    expect((await json<Page<Order>>(await customer.api.listOrders())).total).toBe(1);
  });

  test('reusing a key with a different body is a 409 conflict', async ({ customer, testData }) => {
    const product = await testData.createProduct({ inventory: 10 });
    const key = uniqueIdempotencyKey();
    await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 1 }] }, { idempotencyKey: key });
    const response = await customer.api.createOrder(
      { items: [{ product_id: product.id, quantity: 2 }] },
      { idempotencyKey: key },
    );
    await expect(response).toBeApiError(409, 'IDEMPOTENCY_KEY_REUSED');
  });

  test('without a key, two identical requests create two orders (documented behaviour)', async ({
    customer,
    testData,
  }) => {
    const product = await testData.createProduct({ inventory: 10 });
    const body = { items: [{ product_id: product.id, quantity: 1 }] };
    await expect(await customer.api.createOrder(body)).toHaveStatus(201);
    await expect(await customer.api.createOrder(body)).toHaveStatus(201);
    expect((await json<Page<Order>>(await customer.api.listOrders())).total).toBe(2);
  });

  for (const key of ['has space', 'x'.repeat(65), 'semi;colon']) {
    test(`malformed Idempotency-Key "${key.slice(0, 12)}" is rejected`, async ({ customer, testData }) => {
      const product = await testData.createProduct();
      const response = await customer.api.createOrder(
        { items: [{ product_id: product.id, quantity: 1 }] },
        { idempotencyKey: key },
      );
      await expect(response).toBeApiError(422, 'VALIDATION_ERROR');
    });
  }
});
