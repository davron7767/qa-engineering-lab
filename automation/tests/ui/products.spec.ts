import { test, expect } from '../../fixtures/test';
import { seedProducts } from '../../data/seed';
import { ProductDetailPage, ProductsPage } from '../../pages/products-page';

test.describe('Product catalogue UI', () => {
  test('lists seeded products with price and availability', { tag: '@smoke' }, async ({ page }) => {
    const products = new ProductsPage(page);
    await products.goto();
    await expect(products.heading).toBeVisible();

    const keyboard = products.row(seedProducts.keyboard.sku);
    await expect(keyboard).toContainText(seedProducts.keyboard.name);
    await expect(keyboard).toContainText('$89.99');
    await expect(keyboard).toContainText('in stock');
    await expect(products.row(seedProducts.hub.sku)).toContainText('Out of stock');
    await expect(products.row(seedProducts.laptopStand.sku)).toContainText('Unavailable');
  });

  test('search filters the list', async ({ page }) => {
    const products = new ProductsPage(page);
    await products.goto();
    await products.search('webcam');
    await expect(page).toHaveURL(/\?q=webcam$/);
    await expect(products.rows).toHaveCount(1);
    await expect(products.row(seedProducts.webcam.sku)).toBeVisible();
  });

  test('search with no matches shows an empty state', async ({ page }) => {
    const products = new ProductsPage(page);
    await products.goto();
    await products.search('no-such-product-xyz');
    await expect(page.getByRole('status')).toHaveText('No products match your search.');
  });

  test('product details show price, stock and an order form', async ({ customerPage: page, testData }) => {
    const product = await testData.createProduct({ price: '42.50', inventory: 7, description: 'Detail test' });
    const detail = new ProductDetailPage(page);
    await detail.goto(product.id);

    await expect(detail.heading(product.name)).toBeVisible();
    await expect(detail.price).toHaveText('$42.50');
    await expect(detail.inventory).toHaveText('7');
    await expect(page.getByText('Detail test')).toBeVisible();
    await expect(detail.placeOrder).toBeEnabled();
  });

  test('inactive product cannot be ordered from its page', async ({ customerPage: page, testData, adminApi }) => {
    const product = await testData.createProduct();
    await adminApi.updateProduct(product.id, { is_active: false });
    const detail = new ProductDetailPage(page);
    await detail.goto(product.id);
    await expect(detail.notice).toHaveText('This product is no longer available for ordering.');
    await expect(detail.placeOrder).toHaveCount(0);
  });

  test('unknown product shows a friendly 404 page', async ({ page }) => {
    const response = await page.goto('/products/2147483647');
    expect(response?.status()).toBe(404);
    await expect(page.getByRole('heading', { name: 'Product not found' })).toBeVisible();
  });
});
