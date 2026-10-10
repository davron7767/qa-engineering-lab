import { defineConfig, devices } from '@playwright/test';
import { env } from './utils/env';

/**
 * Projects
 *   api        - REST API tests (no browser)
 *   regression - boundary, atomicity and concurrency scenarios (API level)
 *   chromium   - UI and end-to-end tests (PR gate)
 *   firefox / webkit - same UI/e2e tests, run by the nightly workflow only
 *
 * Retries are deliberately 0 everywhere: a flaky test is a defect to fix, not to hide.
 * The nightly workflow uses --repeat-each on concurrency tests to surface flakiness instead.
 */
const browserTests = ['ui/**/*.spec.ts', 'e2e/**/*.spec.ts'];

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: env.isCI,
  retries: 0,
  workers: env.isCI ? 2 : undefined,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  globalSetup: './global-setup.ts',
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['junit', { outputFile: 'test-results/junit.xml' }],
    ['json', { outputFile: 'test-results/results.json' }],
  ],
  use: {
    baseURL: env.baseUrl,
    testIdAttribute: 'data-testid',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    extraHTTPHeaders: { Accept: 'application/json' },
  },
  projects: [
    { name: 'api', testMatch: 'api/**/*.spec.ts' },
    { name: 'regression', testMatch: 'regression/**/*.spec.ts' },
    { name: 'chromium', testMatch: browserTests, use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', testMatch: browserTests, use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', testMatch: browserTests, use: { ...devices['Desktop Safari'] } },
  ],
});
