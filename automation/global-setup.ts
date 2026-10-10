import { request, type FullConfig } from '@playwright/test';
import { env } from './utils/env';

/**
 * Fail fast with an actionable message if the environment is not ready, instead of letting
 * hundreds of tests fail with connection errors.
 */
export default async function globalSetup(_config: FullConfig): Promise<void> {
  const context = await request.newContext({ baseURL: env.baseUrl });
  try {
    const deadline = Date.now() + 30_000;
    let lastError = '';
    while (Date.now() < deadline) {
      try {
        const health = await context.get('/api/v1/health', { timeout: 5_000 });
        if (health.ok()) break;
        lastError = `HTTP ${health.status()}: ${await health.text()}`;
      } catch (error) {
        lastError = String(error);
      }
      await new Promise((resolve) => setTimeout(resolve, 1_000));
    }
    const health = await context.get('/api/v1/health');
    if (!health.ok()) {
      throw new Error(
        `QA Commerce is not ready at ${env.baseUrl} (${lastError}).\n` +
          'Start it with "docker compose up -d" (or scripts/local-app.ps1) and retry.',
      );
    }

    const login = await context.post('/api/v1/auth/login', {
      data: { email: env.adminEmail, password: env.adminPassword },
    });
    if (!login.ok()) {
      throw new Error(
        `Seeded admin login failed (HTTP ${login.status()}). Is SEED_ON_STARTUP=true and do ` +
          'SEED_ADMIN_PASSWORD values match between the app and the test environment?',
      );
    }
  } finally {
    await context.dispose();
  }
}
