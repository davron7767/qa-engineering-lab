import { test, expect, json } from '../../fixtures/test';
import type { Order, Page } from '../../clients/types';
import { seedProducts } from '../../data/seed';

test.describe('Orders API - placement', () => {
  test('places an order with server-calculated totals', { tag: '@smoke' }, async ({ customer, testData }) => {
    const a = await testData.createProduct({ price: '12.50', inventory: 10 });
    const b = await testData.createProduct({ price: '0.99', inventory: 10 });

    const response = await customer.api.createOrder({
      items: [
        { product_id: a.id, quantity: 2 },
        { product_id: b.id, quantity: 3 },
      ],
    });

    await expect(response).toHaveStatus(201);
    const order = (await response.json()) as Order;
    expect(order).toMatchSchema('order');
    expect(response.headers()['location']).toBe(`/api/v1/orders/${order.id}`);
    expect(order).toMatchObject({
      status: 'confirmed',
      currency: 'USD',
      customer_ref: customer.user.customer_ref,
      total: '27.97',
    });
    expect(order.items).toEqual([
      expect.objectContaining({ product_id: a.id, quantity: 2, unit_price: '12.50', line_total: '25.00' }),
      expect.objectContaining({ product_id: b.id, quantity: 3, unit_price: '0.99', line_total: '2.97' }),
    ]);
  });

  test('decrements inventory by the ordered quantity', async ({ customer, testData, api }) => {
    const product = await testData.createProduct({ inventory: 10 });
    await expect(await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 4 }] })).toHaveStatus(
      201,
    );
    expect((await (await api.getInventory(product.id)).json()).available).toBe(6);
  });

  test('ordering the entire remaining stock is allowed', async ({ customer, testData, api }) => {
    const product = await testData.createProduct({ inventory: 3 });
    await expect(await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 3 }] })).toHaveStatus(
      201,
    );
    expect(await (await api.getInventory(product.id)).json()).toMatchObject({ available: 0, in_stock: false });
  });

  test('unauthenticated order is rejected', async ({ api, testData }) => {
    const product = await testData.createProduct();
    await expect(await api.createOrder({ items: [{ product_id: product.id, quantity: 1 }] })).toBeApiError(
      401,
      'AUTHENTICATION_REQUIRED',
    );
  });
});

test.describe('Orders API - business-rule rejections leave state unchanged', () => {
  test('insufficient inventory: 409 with details, nothing decremented', async ({ customer, testData, api }) => {
    const product = await testData.createProduct({ inventory: 2 });
    const response = await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 3 }] });
    await expect(response).toBeApiError(409, 'INSUFFICIENT_INVENTORY');
    expect((await response.json()).error.details).toEqual([
      { product_id: product.id, sku: product.sku, requested: 3, available: 2 },
    ]);
    expect((await (await api.getInventory(product.id)).json()).available).toBe(2);
    expect((await (await customer.api.listOrders()).json()).total).toBe(0);
  });

  test('one short line rejects the whole multi-line order', async ({ customer, testData, api }) => {
    const plenty = await testData.createProduct({ inventory: 100 });
    const scarce = await testData.createProduct({ inventory: 1 });
    const response = await customer.api.createOrder({
      items: [
        { product_id: plenty.id, quantity: 5 },
        { product_id: scarce.id, quantity: 2 },
      ],
    });
    await expect(response).toBeApiError(409, 'INSUFFICIENT_INVENTORY');
    expect((await (await api.getInventory(plenty.id)).json()).available).toBe(100);
    expect((await (await api.getInventory(scarce.id)).json()).available).toBe(1);
  });

  test('inactive product: 400 PRODUCT_INACTIVE', async ({ customer, testData, adminApi, api }) => {
    const product = await testData.createProduct({ inventory: 5 });
    await adminApi.updateProduct(product.id, { is_active: false });
    const response = await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 1 }] });
    await expect(response).toBeApiError(400, 'PRODUCT_INACTIVE');
    expect((await response.json()).error.details).toEqual([{ product_id: product.id, sku: product.sku }]);
    expect((await (await api.getInventory(product.id)).json()).available).toBe(5);
  });

  test('seeded inactive product cannot be ordered', async ({ customer, api }) => {
    const search = (await (await api.listProducts({ search: seedProducts.laptopStand.sku })).json()) as Page<{
      id: number;
    }>;
    const response = await customer.api.createOrder({ items: [{ product_id: search.items[0]!.id, quantity: 1 }] });
    await expect(response).toBeApiError(400, 'PRODUCT_INACTIVE');
  });

  test('nonexistent product: 400 UNKNOWN_PRODUCT', async ({ customer }) => {
    const response = await customer.api.createOrder({ items: [{ product_id: 2147483647, quantity: 1 }] });
    await expect(response).toBeApiError(400, 'UNKNOWN_PRODUCT');
    expect((await response.json()).error.details).toEqual([{ product_id: 2147483647 }]);
  });
});

test.describe('Orders API - request validation', () => {
  const cases: Array<[string, unknown, string]> = [
    ['missing items', {}, 'items'],
    ['empty items', { items: [] }, 'items'],
    ['missing quantity', { items: [{ product_id: 1 }] }, 'quantity'],
    ['missing product_id', { items: [{ quantity: 1 }] }, 'product_id'],
    ['string quantity', { items: [{ product_id: 1, quantity: '2' }] }, 'quantity'],
    ['float quantity', { items: [{ product_id: 1, quantity: 1.5 }] }, 'quantity'],
    ['boolean quantity', { items: [{ product_id: 1, quantity: true }] }, 'quantity'],
    ['null quantity', { items: [{ product_id: 1, quantity: null }] }, 'quantity'],
    ['items is an object', { items: { product_id: 1, quantity: 1 } }, 'items'],
    ['client-supplied total', { items: [{ product_id: 1, quantity: 1 }], total: '0.01' }, 'total'],
    ['client-supplied unit_price', { items: [{ product_id: 1, quantity: 1, unit_price: '0.01' }] }, 'unit_price'],
  ];

  for (const [name, body, field] of cases) {
    test(`${name} -> 422 pointing at "${field}"`, async ({ customer }) => {
      const response = await customer.api.createOrder(body);
      await expect(response).toBeApiError(422, 'VALIDATION_ERROR');
      const locations = (await response.json()).error.details.map((d: { loc: unknown[] }) => d.loc.join('.'));
      expect(
        locations.some((loc: string) => loc.includes(field)),
        `locations: ${locations}`,
      ).toBe(true);
    });
  }

  test('malformed JSON -> 422', async ({ customer }) => {
    const response = await customer.api.send('POST', '/api/v1/orders', '{"items": [', {
      headers: { 'Content-Type': 'application/json' },
    });
    await expect(response).toBeApiError(422, 'VALIDATION_ERROR');
  });
});

test.describe('Orders API - retrieval, history and cancellation', () => {
  test('customer retrieves own order; another customer gets 404', async ({ customer, testData }) => {
    const product = await testData.createProduct();
    const order = (await (
      await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 1 }] })
    ).json()) as Order;

    const own = await customer.api.getOrder(order.id);
    await expect(own).toHaveStatus(200);
    expect(await json(own)).toEqual(order);

    const other = await testData.createCustomer();
    await expect(await other.api.getOrder(order.id)).toBeApiError(404, 'ORDER_NOT_FOUND');
  });

  test('unknown order id returns 404, malformed id returns 422', async ({ customer }) => {
    await expect(await customer.api.getOrder('00000000-0000-4000-8000-000000000000')).toBeApiError(
      404,
      'ORDER_NOT_FOUND',
    );
    await expect(await customer.api.getOrder('not-a-uuid')).toBeApiError(422, 'VALIDATION_ERROR');
  });

  test('history is newest-first, paginated and scoped to the customer', async ({ customer, testData }) => {
    const product = await testData.createProduct({ inventory: 100 });
    const ids: string[] = [];
    for (let i = 0; i < 3; i++) {
      const order = await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 1 }] });
      ids.push((await order.json()).id);
    }

    const page1 = await customer.api.listOrders({ page: 1, page_size: 2 });
    await expect(page1).toHaveStatus(200);
    const body1 = (await page1.json()) as Page<Order>;
    expect(body1).toMatchSchema('order-page');
    expect(body1).toMatchObject({ total: 3, pages: 2, page: 1, page_size: 2 });

    const body2 = (await (await customer.api.listOrders({ page: 2, page_size: 2 })).json()) as Page<Order>;
    expect([...body1.items, ...body2.items].map((o) => o.id)).toEqual([...ids].reverse());

    const outOfRange = (await (await customer.api.listOrders({ page: 99 })).json()) as Page<Order>;
    expect(outOfRange.items).toEqual([]);
  });

  test('cancelling restores inventory exactly once', async ({ customer, testData, api }) => {
    const product = await testData.createProduct({ inventory: 10 });
    const order = (await (
      await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 4 }] })
    ).json()) as Order;

    const cancelled = await customer.api.cancelOrder(order.id);
    await expect(cancelled).toHaveStatus(200);
    expect((await cancelled.json()).status).toBe('cancelled');
    expect((await (await api.getInventory(product.id)).json()).available).toBe(10);

    await expect(await customer.api.cancelOrder(order.id)).toBeApiError(409, 'ORDER_NOT_CANCELLABLE');
    expect((await (await api.getInventory(product.id)).json()).available).toBe(10);
  });
});
