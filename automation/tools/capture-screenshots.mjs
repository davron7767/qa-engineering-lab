/**
 * Regenerates the README screenshots from the running application and real Playwright reports.
 *
 * Prerequisites: app running at BASE_URL, `npm test` has produced playwright-report/, and
 * (optionally) the defect lab has produced defect-lab-report/inventory_before_validation/.
 * Uses fresh, isolated data created through the admin API; seed records are never modified.
 *
 * Usage (from automation/): node tools/capture-screenshots.mjs
 */
import { chromium, request } from '@playwright/test';
import { existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const baseURL = process.env.BASE_URL ?? 'http://localhost:8000';
const outDir = path.resolve('..', 'docs', 'images');
mkdirSync(outDir, { recursive: true });

const suffix = Date.now().toString(36).toUpperCase();
const api = await request.newContext({ baseURL });
const adminLogin = await (
  await api.post('/api/v1/auth/login', {
    data: { email: 'admin@qa-commerce.test', password: process.env.SEED_ADMIN_PASSWORD ?? 'Admin#Local2024' },
  })
).json();
const admin = { Authorization: `Bearer ${adminLogin.access_token}` };
const product = await (
  await api.post('/api/v1/products', {
    headers: admin,
    data: { sku: `SHOT-${suffix}`, name: 'Ergonomic Desk Mat', price: '24.99', inventory: 40 },
  })
).json();
const email = `screenshots-${suffix.toLowerCase()}@qa-commerce.test`;
const password = 'Screenshot#Local1';
await api.post('/api/v1/users', { headers: admin, data: { email, full_name: 'Sam Screenshot', password } });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

await page.goto(`${baseURL}/login`);
await page.getByLabel('Email').fill(email);
await page.getByLabel('Password').fill(password);
await page.getByRole('button', { name: 'Log in' }).click();
await page.goto(`${baseURL}/products?q=QA-`);
await page.screenshot({ path: path.join(outDir, 'ui-products.png'), fullPage: true });

await page.goto(`${baseURL}/products/${product.id}`);
await page.getByLabel('Quantity').fill('3');
await page.getByRole('button', { name: 'Place order' }).click();
await page.getByText('Order confirmed').waitFor();
await page.screenshot({ path: path.join(outDir, 'ui-order-confirmation.png'), fullPage: true });

await page.goto(`${baseURL}/orders/new`);
await page.getByLabel('Quantity for Ergonomic Desk Mat', { exact: true }).fill('999');
await page.getByRole('button', { name: 'Place order' }).click();
await page.getByRole('alert').waitFor();
await page.screenshot({ path: path.join(outDir, 'ui-insufficient-inventory.png'), fullPage: true });

const report = path.resolve('playwright-report', 'index.html');
if (existsSync(report)) {
  await page.goto(pathToFileURL(report).href);
  await page.getByText('passed', { exact: false }).first().waitFor();
  await page.screenshot({ path: path.join(outDir, 'report-passing.png') });
}

const defectReport = path.resolve('defect-lab-report', 'inventory_before_validation', 'index.html');
if (existsSync(defectReport)) {
  await page.goto(pathToFileURL(defectReport).href);
  await page
    .getByRole('link', { name: /one short line rejects/ })
    .first()
    .click();
  await page.getByText('Expected: 100').first().waitFor();
  // Privacy: shorten absolute source paths (which contain the local user name) to repo-relative.
  await page.evaluate(
    (root) => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.textContent.includes(root)) node.textContent = node.textContent.split(root).join('');
      }
    },
    path.resolve('..') + path.sep,
  );
  await page.screenshot({ path: path.join(outDir, 'report-defect-detected.png'), fullPage: true });
}

// Retire the screenshot product so it does not clutter the catalogue.
await api.patch(`/api/v1/products/${product.id}`, { headers: admin, data: { is_active: false } });
await browser.close();
await api.dispose();
console.log(`Screenshots written to ${outDir}`);
