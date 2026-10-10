import type { Locator, Page } from '@playwright/test';

export class ProductsPage {
  readonly heading: Locator;
  readonly searchBox: Locator;
  readonly rows: Locator;

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { name: 'Products', level: 1 });
    this.searchBox = page.getByRole('searchbox', { name: 'Search products' });
    this.rows = page.getByTestId('product-row');
  }

  async goto(): Promise<void> {
    await this.page.goto('/products');
  }

  async search(term: string): Promise<void> {
    await this.searchBox.fill(term);
    await this.page.getByRole('button', { name: 'Search' }).click();
  }

  row(sku: string): Locator {
    return this.page.locator(`[data-testid="product-row"][data-sku="${sku}"]`);
  }

  async openProduct(name: string): Promise<void> {
    await this.page.getByRole('link', { name, exact: true }).click();
  }
}

export class ProductDetailPage {
  readonly price: Locator;
  readonly inventory: Locator;
  readonly quantity: Locator;
  readonly placeOrder: Locator;
  readonly notice: Locator;

  constructor(private readonly page: Page) {
    this.price = page.getByTestId('product-price');
    this.inventory = page.getByTestId('product-inventory');
    this.quantity = page.getByLabel('Quantity');
    this.placeOrder = page.getByRole('button', { name: 'Place order' });
    this.notice = page.getByRole('status');
  }

  async goto(productId: number): Promise<void> {
    await this.page.goto(`/products/${productId}`);
  }

  heading(name: string): Locator {
    return this.page.getByRole('heading', { name, level: 1 });
  }

  async order(quantity: number | string): Promise<void> {
    await this.quantity.fill(String(quantity));
    await this.placeOrder.click();
  }
}
