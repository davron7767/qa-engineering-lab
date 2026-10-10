import { test, expect, json } from '../../fixtures/test';
import type { Inventory, Order, Product } from '../../clients/types';
import { OrderDetailPage, OrderHistoryPage } from '../../pages/order-pages';
import { db } from '../../utils/db';

/**
 * Workflow: prepare data via API -> authenticate via API -> read product -> place order via API
 * -> verify in the UI -> verify persisted order and inventory in the database -> cancel in UI
 * -> verify restoration through API and database.
 */
test(
  'order placed through the API is visible and cancellable in the UI',
  { tag: ['@e2e', '@smoke'] },
  async ({ testData, customer, customerPage: page, api }) => {
    // 1. Prepare known, isolated test data.
    const created = await testData.createProduct({ price: '24.99', inventory: 8 });

    // 2-3. Authenticated customer (fixture) retrieves product information.
    const product = await json<Product>(await customer.api.getProduct(created.id));
    expect(product).toMatchObject({ price: '24.99', inventory: 8, is_active: true });

    // 4. Create the order through the API.
    const response = await customer.api.createOrder({ items: [{ product_id: product.id, quantity: 3 }] });
    await expect(response).toHaveStatus(201);
    const order = await json<Order>(response);
    expect(order.total).toBe('74.97');

    // 5. Verify it in the UI: history row and detail page.
    const history = new OrderHistoryPage(page);
    await history.goto();
    await expect(history.row(order.id)).toContainText('$74.97');
    await history.row(order.id).getByRole('link').click();

    const detail = new OrderDetailPage(page);
    await expect(detail.orderId).toHaveText(order.id);
    await expect(detail.status).toHaveText('Confirmed');
    await expect(detail.line(product.sku)).toContainText('3');
    await expect(detail.total).toHaveText('$74.97');

    // 6. Verify persisted state directly in the database.
    expect(await db.order(order.id)).toMatchObject({
      status: 'confirmed',
      total: '74.97',
      customer_ref: customer.user.customer_ref,
    });
    expect(await db.orderItems(order.id)).toEqual([
      { product_id: product.id, sku: product.sku, quantity: 3, unit_price: '24.99', line_total: '74.97' },
    ]);
    expect(await db.productInventory(product.id)).toBe(5);

    // 7. Cancel in the UI and confirm restoration everywhere.
    await detail.cancel.click();
    await expect(detail.status).toHaveText('Cancelled');
    expect((await json<Inventory>(await api.getInventory(product.id))).available).toBe(8);
    expect((await db.order(order.id))?.status).toBe('cancelled');
    expect(await db.productInventory(product.id)).toBe(8);
  },
);
