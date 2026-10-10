import { defineConfig, devices } from '@playwright/test';
import { env } from './utils/env';

/**
 * Projects
 *   api        - REST API tests (no browser)
 *   regression - boundary, atomicity and concurrency scenarios (API level)
 *   chromium   - UI and end-to-end tests (PR gate)
 *   firefox / webkit - same UI/e2e tests, run by the nightly workflow only
 *
 * Browser traces (UI/e2e) contain the synthetic test accounts' session cookies and typed
 * passwords; acceptable for this local-only lab, never point the suite at real credentials.
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
  outputDir: `${env.resultsDir}/artifacts`,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: env.reportDir }],
    ['junit', { outputFile: `${env.resultsDir}/junit.xml` }],
    ['json', { outputFile: `${env.resultsDir}/results.json` }],
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
    // API projects record a redacted HTTP log instead of a trace: Playwright traces capture raw
    // Authorization headers and login bodies, which must not end up in CI artifacts.
    { name: 'api', testMatch: 'api/**/*.spec.ts', use: { trace: 'off' } },
    { name: 'regression', testMatch: 'regression/**/*.spec.ts', use: { trace: 'off' } },
    { name: 'chromium', testMatch: browserTests, use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', testMatch: browserTests, use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', testMatch: browserTests, use: { ...devices['Desktop Safari'] } },
  ],
});
