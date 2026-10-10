import type { Locator, Page } from '@playwright/test';

export class NewOrderPage {
  readonly heading: Locator;
  readonly submit: Locator;
  readonly errors: Locator;

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { name: 'New order' });
    this.submit = page.getByRole('button', { name: 'Place order' });
    this.errors = page.getByRole('alert');
  }

  async goto(): Promise<void> {
    await this.page.goto('/orders/new');
  }

  quantityFor(productName: string): Locator {
    return this.page.getByLabel(`Quantity for ${productName}`, { exact: true });
  }

  async setQuantity(productName: string, quantity: number | string): Promise<void> {
    await this.quantityFor(productName).fill(String(quantity));
  }
}

export class OrderDetailPage {
  readonly confirmation: Locator;
  readonly orderId: Locator;
  readonly status: Locator;
  readonly total: Locator;
  readonly lines: Locator;
  readonly cancel: Locator;

  constructor(private readonly page: Page) {
    this.confirmation = page.getByRole('status').filter({ hasText: 'Order confirmed' });
    this.orderId = page.getByTestId('order-id');
    this.status = page.getByTestId('order-status');
    this.total = page.getByTestId('order-total');
    this.lines = page.getByTestId('order-line');
    this.cancel = page.getByRole('button', { name: 'Cancel order' });
  }

  async goto(orderId: string): Promise<void> {
    await this.page.goto(`/orders/${orderId}`);
  }

  line(sku: string): Locator {
    return this.page.locator(`[data-testid="order-line"][data-sku="${sku}"]`);
  }

  /** The order id from the URL after the post-submit redirect. */
  idFromUrl(): string {
    const match = /\/orders\/([0-9a-f-]{36})/.exec(this.page.url());
    if (!match?.[1]) throw new Error(`Not on an order page: ${this.page.url()}`);
    return match[1];
  }
}

export class OrderHistoryPage {
  readonly heading: Locator;
  readonly rows: Locator;
  readonly empty: Locator;
  readonly pagination: Locator;

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { name: 'Order history' });
    this.rows = page.getByTestId('order-row');
    this.empty = page.getByText('You have not placed any orders yet.');
    this.pagination = page.getByRole('navigation', { name: 'Pagination' });
  }

  async goto(pageNumber = 1): Promise<void> {
    await this.page.goto(pageNumber === 1 ? '/orders' : `/orders?page=${pageNumber}`);
  }

  row(orderId: string): Locator {
    return this.page.locator(`[data-testid="order-row"][data-order-id="${orderId}"]`);
  }
}
