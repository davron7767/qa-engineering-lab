import { test, expect, json } from '../../fixtures/test';
import type { Page, Product } from '../../clients/types';
import { seedProducts } from '../../data/seed';
import { productInput, uniqueSku } from '../../data/factories';

test.describe('Products API - catalogue', () => {
  test('lists products with a valid page envelope', { tag: '@smoke' }, async ({ api }) => {
    const response = await api.listProducts({ page_size: 100 });
    await expect(response).toHaveStatus(200);
    const body = (await response.json()) as Page<Product>;
    expect(body).toMatchSchema('product-page');
    const skus = body.items.map((p) => p.sku);
    for (const seed of Object.values(seedProducts)) expect(skus).toContain(seed.sku);
  });

  test('search matches name, SKU and description case-insensitively', async ({ api }) => {
    for (const term of ['wireless', 'QA-MS-002', 'ergonomic']) {
      const body = (await (await api.listProducts({ search: term })).json()) as Page<Product>;
      expect(
        body.items.map((p) => p.sku),
        `search "${term}"`,
      ).toContain(seedProducts.mouse.sku);
    }
  });

  test('active=false returns only inactive products', async ({ api }) => {
    const body = (await (await api.listProducts({ active: false, page_size: 100 })).json()) as Page<Product>;
    expect(body.items.length).toBeGreaterThan(0);
    expect(body.items.every((p) => !p.is_active)).toBe(true);
    expect(body.items.map((p) => p.sku)).toContain(seedProducts.laptopStand.sku);
  });

  test('price range filter is inclusive', async ({ api, testData }) => {
    const product = await testData.createProduct({ price: '123.45' });
    const response = await api.listProducts({ min_price: '123.45', max_price: '123.45', search: product.sku });
    const body = (await response.json()) as Page<Product>;
    expect(body.items.map((p) => p.sku)).toEqual([product.sku]);
  });

  test('min_price greater than max_price is a validation error', async ({ api }) => {
    await expect(await api.listProducts({ min_price: 10, max_price: 5 })).toBeApiError(422, 'VALIDATION_ERROR');
  });

  test('retrieves a product and its inventory consistently', async ({ api, testData }) => {
    const created = await testData.createProduct({ inventory: 42 });
    const product = await api.getProduct(created.id);
    await expect(product).toHaveStatus(200);
    expect(await json(product)).toMatchSchema('product');

    const inventory = await api.getInventory(created.id);
    await expect(inventory).toHaveStatus(200);
    const body = await json(inventory);
    expect(body).toMatchSchema('inventory');
    expect(body).toMatchObject({ product_id: created.id, sku: created.sku, available: 42, in_stock: true });
  });

  test('nonexistent product id returns 404 PRODUCT_NOT_FOUND', async ({ api }) => {
    await expect(await api.getProduct(2147483647)).toBeApiError(404, 'PRODUCT_NOT_FOUND');
    await expect(await api.getInventory(2147483647)).toBeApiError(404, 'PRODUCT_NOT_FOUND');
  });

  for (const id of ['0', '-1', 'abc', '2147483648']) {
    test(`invalid product id "${id}" returns 422`, async ({ api }) => {
      await expect(await api.getProduct(id)).toBeApiError(422, 'VALIDATION_ERROR');
    });
  }
});

test.describe('Products API - administration', () => {
  test('admin creates a product; server echoes normalised values', async ({ adminApi }) => {
    const input = productInput({ price: 19.9, inventory: 5 });
    const response = await adminApi.createProduct(input);
    await expect(response).toHaveStatus(201);
    const body = await json<Product>(response);
    expect(body).toMatchSchema('product');
    expect(body).toMatchObject({ sku: input.sku, price: '19.90', inventory: 5, is_active: true, in_stock: true });
    await adminApi.updateProduct(body.id, { is_active: false });
  });

  test('duplicate SKU returns 409 SKU_ALREADY_EXISTS', async ({ adminApi, testData }) => {
    const existing = await testData.createProduct();
    await expect(await adminApi.createProduct(productInput({ sku: existing.sku }))).toBeApiError(
      409,
      'SKU_ALREADY_EXISTS',
    );
  });

  for (const [name, overrides] of [
    ['zero price', { price: '0' }],
    ['negative price', { price: '-1.00' }],
    ['three decimal places', { price: '1.005' }],
    ['non-numeric price', { price: 'free' }],
    ['negative inventory', { inventory: -1 }],
    ['fractional inventory', { inventory: 1.5 }],
  ] as const) {
    test(`rejects ${name} and does not create the product`, async ({ adminApi, api }) => {
      const sku = uniqueSku('BAD');
      const response = await adminApi.createProduct({ ...productInput({ sku }), ...overrides });
      await expect(response).toBeApiError(422, 'VALIDATION_ERROR');
      const search = (await (await api.listProducts({ search: sku })).json()) as Page<Product>;
      expect(search.total).toBe(0);
    });
  }

  test('inventory can be set to zero but not below', async ({ adminApi, testData }) => {
    const product = await testData.createProduct({ inventory: 3 });
    const zero = await adminApi.setInventory(product.id, 0);
    await expect(zero).toHaveStatus(200);
    expect(await zero.json()).toMatchObject({ available: 0, in_stock: false });
    await expect(await adminApi.setInventory(product.id, -1)).toBeApiError(422, 'VALIDATION_ERROR');
    expect((await (await adminApi.getInventory(product.id)).json()).available).toBe(0);
  });

  test('customers cannot modify the catalogue', async ({ customer, testData }) => {
    const product = await testData.createProduct();
    await expect(await customer.api.createProduct(productInput())).toBeApiError(403, 'FORBIDDEN');
    await expect(await customer.api.setInventory(product.id, 999)).toBeApiError(403, 'FORBIDDEN');
    await expect(await customer.api.updateProduct(product.id, { price: '0.01' })).toBeApiError(403, 'FORBIDDEN');
  });
});
