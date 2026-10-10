import { test, expect } from '../../fixtures/test';
import type { Page } from '@playwright/test';
import { LoginPage } from '../../pages/login-page';

async function expectLoginRedirect(page: Page, next: string): Promise<void> {
  await expect(page).toHaveURL(/\/login\?/);
  expect(new URL(page.url()).searchParams.get('next')).toBe(next);
}

test.describe('Login', () => {
  test('customer logs in and sees their name', { tag: '@smoke' }, async ({ page, customer }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.login(customer.email, customer.password);

    await expect(page).toHaveURL(/\/products$/);
    await expect(page.getByTestId('current-user')).toHaveText('Signed in as Playwright Customer');
  });

  test('wrong password shows an error and keeps the email', async ({ page, customer }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.login(customer.email, 'wrong-password');

    await expect(login.error).toHaveText('Invalid email or password.');
    await expect(login.email).toHaveValue(customer.email);
    await expect(login.password).toHaveValue('');
  });

  test('empty submission shows a validation message', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.submit.click();
    await expect(login.error).toHaveText('Email and password are required.');
  });

  test('logout ends the session', async ({ customerPage: page }) => {
    await page.goto('/orders');
    await page.getByRole('button', { name: 'Log out' }).click();

    await expect(page.getByRole('status')).toHaveText('You have been logged out.');
    await page.goto('/orders');
    await expectLoginRedirect(page, '/orders');
  });
});

test.describe('Unauthenticated navigation', () => {
  for (const path of ['/orders', '/orders/new']) {
    test(`${path} redirects to login and returns after signing in`, async ({ page, customer }) => {
      await page.goto(path);
      await expectLoginRedirect(page, path);

      await new LoginPage(page).login(customer.email, customer.password);
      await expect(page).toHaveURL(new RegExp(`${path}$`));
    });
  }

  test('anonymous visitor can browse products but must log in to order', async ({ page }) => {
    await page.goto('/products');
    await expect(page.getByRole('link', { name: 'Log in' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'New order' })).toHaveCount(0);
  });

  test('open redirects are blocked', async ({ page, customer }) => {
    await page.goto('/login?next=//evil.example/phish');
    await new LoginPage(page).login(customer.email, customer.password);
    await expect(page).toHaveURL(/localhost:\d+\/products$/);
  });
});
