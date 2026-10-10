/**
 * Runtime configuration for the automation suite. Every value has a local default that matches
 * .env.example, so `npx playwright test` works against the default local stack.
 */
function read(name: string, fallback: string): string {
  const value = process.env[name];
  return value === undefined || value === '' ? fallback : value;
}

export const env = {
  isCI: !!process.env.CI,
  baseUrl: read('BASE_URL', 'http://localhost:8000'),
  /** Overridable so the defect lab never overwrites the normal reports. */
  reportDir: read('PW_REPORT_DIR', 'playwright-report'),
  resultsDir: read('PW_RESULTS_DIR', 'test-results'),
  /** Read-only database checks. Points at the same database the app under test uses. */
  databaseUrl: read('AUTOMATION_DATABASE_URL', 'postgresql://qa_commerce:qa_commerce_local@localhost:5433/qa_commerce'),
  adminEmail: read('SEED_ADMIN_EMAIL', 'admin@qa-commerce.test'),
  adminPassword: read('SEED_ADMIN_PASSWORD', 'Admin#Local2024'),
  customerEmail: read('SEED_CUSTOMER_EMAIL', 'customer@qa-commerce.test'),
  customerPassword: read('SEED_CUSTOMER_PASSWORD', 'Customer#Local2024'),
} as const;
