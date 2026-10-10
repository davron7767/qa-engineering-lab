import { test, expect } from '../../fixtures/test';
import { NewOrderPage, OrderDetailPage, OrderHistoryPage } from '../../pages/order-pages';
import { ProductDetailPage } from '../../pages/products-page';

test.describe('Placing orders in the UI', () => {
  test(
    'order from the product page shows a confirmation',
    { tag: '@smoke' },
    async ({ customerPage: page, testData }) => {
      const product = await testData.createProduct({ price: '15.25', inventory: 5 });
      await new ProductDetailPage(page).goto(product.id);
      await new ProductDetailPage(page).order(2);

      const order = new OrderDetailPage(page);
      await expect(order.confirmation).toBeVisible();
      await expect(order.status).toHaveText('Confirmed');
      await expect(order.line(product.sku)).toContainText('$30.50');
      await expect(order.total).toHaveText('$30.50');
    },
  );

  test('multi-product order from the New order form', async ({ customerPage: page, testData }) => {
    const a = await testData.createProduct({ price: '2.50' });
    const b = await testData.createProduct({ price: '0.29' });
    const form = new NewOrderPage(page);
    await form.goto();
    await form.setQuantity(a.name, 2);
    await form.setQuantity(b.name, 3);
    await form.submit.click();

    const order = new OrderDetailPage(page);
    await expect(order.confirmation).toBeVisible();
    await expect(order.lines).toHaveCount(2);
    await expect(order.total).toHaveText('$5.87');
  });

  test('submitting with no quantities shows a validation message', async ({ customerPage: page }) => {
    const form = new NewOrderPage(page);
    await form.goto();
    await form.submit.click();
    await expect(form.errors).toHaveText('Select at least one product by entering a quantity.');
  });

  for (const [value, message] of [
    ['1.5', "Quantity '1.5' is not a whole number."],
    ['-2', 'Quantity must be at least 1.'],
    ['1001', 'Quantity must not exceed 1000.'],
  ] as const) {
    test(`invalid quantity ${value} is rejected and the value is preserved`, async ({
      customerPage: page,
      testData,
    }) => {
      const product = await testData.createProduct();
      const form = new NewOrderPage(page);
      await form.goto();
      await form.setQuantity(product.name, value);
      await form.submit.click();
      await expect(form.errors).toHaveText(message);
      await expect(form.quantityFor(product.name)).toHaveValue(value);
    });
  }

  test('insufficient inventory explains what is available', async ({ customerPage: page, testData, api }) => {
    const product = await testData.createProduct({ inventory: 2 });
    const form = new NewOrderPage(page);
    await form.goto();
    await form.setQuantity(product.name, 3);
    await form.submit.click();

    await expect(form.errors).toHaveText(`Insufficient inventory. ${product.sku}: requested 3, only 2 available.`);
    expect((await (await api.getInventory(product.id)).json()).available).toBe(2);
  });

  test('out-of-stock product page offers no order form', async ({ customerPage: page, testData }) => {
    const product = await testData.createProduct({ inventory: 0 });
    const detail = new ProductDetailPage(page);
    await detail.goto(product.id);
    await expect(detail.notice).toHaveText('This product is out of stock.');
    await expect(detail.placeOrder).toHaveCount(0);
  });

  test('cancelling an order from its page', async ({ customerPage: page, testData, api }) => {
    const product = await testData.createProduct({ inventory: 5 });
    await new ProductDetailPage(page).goto(product.id);
    await new ProductDetailPage(page).order(5);
    const order = new OrderDetailPage(page);
    await expect(order.confirmation).toBeVisible();

    await order.cancel.click();
    await expect(order.status).toHaveText('Cancelled');
    await expect(page.getByRole('status')).toHaveText('Order cancelled. Items were returned to inventory.');
    await expect(order.cancel).toHaveCount(0);
    expect((await (await api.getInventory(product.id)).json()).available).toBe(5);
  });
});

test.describe('Order history UI', () => {
  test('a new customer has an empty history', async ({ customerPage: page }) => {
    const history = new OrderHistoryPage(page);
    await history.goto();
    await expect(history.heading).toBeVisible();
    await expect(history.empty).toBeVisible();
  });

  test('history paginates ten orders per page, newest first', async ({ customerPage: page, customer, testData }) => {
    const product = await testData.createProduct({ inventory: 100 });
    const ids: string[] = [];
    for (let i = 0; i < 11; i++) {
      const response = await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 1 }] });
      ids.push((await response.json()).id);
    }

    const history = new OrderHistoryPage(page);
    await history.goto();
    await expect(history.rows).toHaveCount(10);
    await expect(history.rows.first()).toHaveAttribute('data-order-id', ids[10]!);
    await expect(history.pagination).toContainText('Page 1 of 2');

    await history.pagination.getByRole('link', { name: 'Next page' }).click();
    await expect(history.rows).toHaveCount(1);
    await expect(history.row(ids[0]!)).toBeVisible();
  });

  test("another customer's order is not viewable", async ({ customerPage: page, testData }) => {
    const other = await testData.createCustomer();
    const product = await testData.createProduct();
    const order = await (await other.api.createOrder({ items: [{ product_id: product.id, quantity: 1 }] })).json();

    const response = await page.goto(`/orders/${order.id}`);
    expect(response?.status()).toBe(404);
    await expect(page.getByRole('heading', { name: 'Order not found' })).toBeVisible();
  });
});
