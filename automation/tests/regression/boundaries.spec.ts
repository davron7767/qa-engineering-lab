import { test, expect, json } from '../../fixtures/test';
import type { Order } from '../../clients/types';
import { productInput } from '../../data/factories';

test.describe('Quantity boundaries', { tag: '@regression' }, () => {
  const rejected: Array<[string, unknown]> = [
    ['zero', 0],
    ['negative', -1],
    ['non-integer', 1.5],
    ['integral float', 2.0000001],
    ['above per-line maximum (1001)', 1001],
    ['int32 overflow', 2147483648],
    ['huge number', 1e20],
    ['numeric string', '5'],
  ];

  for (const [name, quantity] of rejected) {
    test(`quantity ${name} is rejected without side effects`, async ({ customer, testData, api }) => {
      const product = await testData.createProduct({ inventory: 5000 });
      const response = await customer.api.createOrder({ items: [{ product_id: product.id, quantity }] });
      await expect(response).toBeApiError(422, 'VALIDATION_ERROR');
      expect((await json<{ available: number }>(await api.getInventory(product.id))).available).toBe(5000);
    });
  }

  test('quantity 1 (minimum) is accepted', async ({ customer, testData }) => {
    const product = await testData.createProduct({ inventory: 1 });
    await expect(await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 1 }] })).toHaveStatus(
      201,
    );
  });

  test('quantity 1000 (per-line maximum) is accepted', async ({ customer, testData }) => {
    const product = await testData.createProduct({ inventory: 1000, price: '0.01' });
    const response = await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 1000 }] });
    await expect(response).toHaveStatus(201);
    expect((await json<Order>(response)).total).toBe('10.00');
  });

  test('a valid but very large quantity beyond stock is an inventory conflict, not a crash', async ({
    customer,
    testData,
  }) => {
    const product = await testData.createProduct({ inventory: 10 });
    const response = await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 999 }] });
    await expect(response).toBeApiError(409, 'INSUFFICIENT_INVENTORY');
  });
});

test.describe('Order shape boundaries', { tag: '@regression' }, () => {
  test('empty order is rejected', async ({ customer }) => {
    await expect(await customer.api.createOrder({ items: [] })).toBeApiError(422, 'VALIDATION_ERROR');
  });

  test('the same product twice in one order is rejected', async ({ customer, testData }) => {
    const product = await testData.createProduct();
    const response = await customer.api.createOrder({
      items: [
        { product_id: product.id, quantity: 1 },
        { product_id: product.id, quantity: 1 },
      ],
    });
    await expect(response).toBeApiError(422, 'VALIDATION_ERROR');
  });

  test('51 line items exceed the per-order maximum', async ({ customer }) => {
    const items = Array.from({ length: 51 }, (_, i) => ({ product_id: i + 1, quantity: 1 }));
    await expect(await customer.api.createOrder({ items })).toBeApiError(422, 'VALIDATION_ERROR');
  });

  test('missing product mixed with a valid product rejects the whole order', async ({ customer, testData, api }) => {
    const product = await testData.createProduct({ inventory: 5 });
    const response = await customer.api.createOrder({
      items: [
        { product_id: product.id, quantity: 1 },
        { product_id: 2147483647, quantity: 1 },
      ],
    });
    await expect(response).toBeApiError(400, 'UNKNOWN_PRODUCT');
    expect((await json<{ available: number }>(await api.getInventory(product.id))).available).toBe(5);
  });
});

test.describe('Price boundaries', { tag: '@regression' }, () => {
  for (const price of ['0.01', '999999.99']) {
    test(`price ${price} is accepted`, async ({ testData }) => {
      const product = await testData.createProduct({ price });
      expect(product.price).toBe(price);
    });
  }

  for (const price of ['0', '0.00', '-0.01', '1000000.00', '0.001', 'NaN', 'Infinity']) {
    test(`price ${price} is rejected`, async ({ adminApi }) => {
      await expect(await adminApi.createProduct(productInput({ price }))).toBeApiError(422, 'VALIDATION_ERROR');
    });
  }
});

test.describe('Decimal currency calculations', { tag: '@regression' }, () => {
  // Each case is a value where naive binary floating point gives a wrong answer
  // (e.g. 0.29 * 3 = 0.8699999999999999 and 0.1 * 3 = 0.30000000000000004).
  const cases: Array<{ name: string; lines: Array<[string, number]>; total: string; lineTotals: string[] }> = [
    { name: '0.29 x 3', lines: [['0.29', 3]], total: '0.87', lineTotals: ['0.87'] },
    { name: '0.10 x 3', lines: [['0.10', 3]], total: '0.30', lineTotals: ['0.30'] },
    { name: '19.99 x 3', lines: [['19.99', 3]], total: '59.97', lineTotals: ['59.97'] },
    { name: '1.15 x 7', lines: [['1.15', 7]], total: '8.05', lineTotals: ['8.05'] },
    {
      name: '0.10 + 0.20 across lines',
      lines: [
        ['0.10', 1],
        ['0.20', 1],
      ],
      total: '0.30',
      lineTotals: ['0.10', '0.20'],
    },
    {
      name: 'max price x max quantity',
      lines: [['999999.99', 1000]],
      total: '999999990.00',
      lineTotals: ['999999990.00'],
    },
  ];

  for (const { name, lines, total, lineTotals } of cases) {
    test(`total for ${name} is exact`, async ({ customer, testData }) => {
      const items = [];
      for (const [price, quantity] of lines) {
        const product = await testData.createProduct({ price, inventory: quantity });
        items.push({ product_id: product.id, quantity });
      }
      const response = await customer.api.createOrder({ items });
      await expect(response).toHaveStatus(201);
      const order = await json<Order>(response);
      expect(order.items.map((i) => i.line_total)).toEqual(lineTotals);
      expect(order.total).toBe(total);
    });
  }
});
