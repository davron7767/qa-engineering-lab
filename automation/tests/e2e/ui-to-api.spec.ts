import { test, expect, json } from '../../fixtures/test';
import type { Inventory, Order, Page } from '../../clients/types';
import { LoginPage } from '../../pages/login-page';
import { NewOrderPage, OrderDetailPage } from '../../pages/order-pages';
import { db } from '../../utils/db';

/**
 * Workflow: log in through the real login form -> place a multi-line order in the UI ->
 * verify the order, totals and inventory through the API and the database.
 */
test(
  'order placed in the UI is correct in the API and database',
  { tag: '@e2e' },
  async ({ page, testData, customer, api }) => {
    const keyboard = await testData.createProduct({ price: '89.99', inventory: 4 });
    const ties = await testData.createProduct({ price: '0.29', inventory: 100 });

    const login = new LoginPage(page);
    await login.goto('/orders/new');
    await login.login(customer.email, customer.password);

    const form = new NewOrderPage(page);
    await expect(form.heading).toBeVisible();
    await form.setQuantity(keyboard.name, 1);
    await form.setQuantity(ties.name, 3);
    await form.submit.click();

    const detail = new OrderDetailPage(page);
    await expect(detail.confirmation).toBeVisible();
    await expect(detail.total).toHaveText('$90.86');
    const orderId = detail.idFromUrl();

    // API view of the same order.
    const order = await json<Order>(await customer.api.getOrder(orderId));
    expect(order).toMatchSchema('order');
    expect(order).toMatchObject({ status: 'confirmed', total: '90.86', customer_ref: customer.user.customer_ref });
    expect(order.items.map((i) => [i.sku, i.quantity, i.line_total])).toEqual(
      expect.arrayContaining([
        [keyboard.sku, 1, '89.99'],
        [ties.sku, 3, '0.87'],
      ]),
    );

    const history = await json<Page<Order>>(await customer.api.listOrders());
    expect(history.items.map((o) => o.id)).toEqual([orderId]);

    // Inventory through the API and the database.
    expect((await json<Inventory>(await api.getInventory(keyboard.id))).available).toBe(3);
    expect((await json<Inventory>(await api.getInventory(ties.id))).available).toBe(97);
    expect(await db.order(orderId)).toMatchObject({ total: '90.86', status: 'confirmed' });

    // The hidden idempotency key from the form was stored, so a resubmitted form cannot duplicate.
    expect((await db.order(orderId))?.idempotency_key).toMatch(/^[0-9a-f]{32}$/);
  },
);

test(
  're-submitting the same order form does not create a duplicate',
  { tag: '@e2e' },
  async ({ customerPage: page, customer, testData }) => {
    const product = await testData.createProduct({ inventory: 10 });
    const form = new NewOrderPage(page);
    await form.goto();
    await form.setQuantity(product.name, 2);

    // Capture exactly what the browser is about to post, including the hidden idempotency key.
    const formData = await page
      .locator('form[action="/orders"]')
      .evaluate((el) =>
        Object.fromEntries(new FormData(el as HTMLFormElement) as unknown as Iterable<[string, string]>),
      );
    await form.submit.click();
    await expect(new OrderDetailPage(page).confirmation).toBeVisible();

    // Replay the identical POST (as a refresh-after-submit or network retry would) with the
    // browser's own cookies. The server must recognise it and not create a second order.
    const replay = await page.request.post('/orders', { form: formData, maxRedirects: 0 });
    expect(replay.status()).toBe(303);

    expect((await json<Page<Order>>(await customer.api.listOrders())).total).toBe(1);
    expect(await db.productInventory(product.id)).toBe(8);
  },
);
