import { test, expect, json } from '../../fixtures/test';
import type { LoginResponse } from '../../clients/types';
import { env } from '../../utils/env';

test.describe('Authentication API', () => {
  test('login returns a bearer token and the user profile', { tag: '@smoke' }, async ({ api }) => {
    const response = await api.login(env.customerEmail, env.customerPassword);
    await expect(response).toHaveStatus(200);
    const body = await json<LoginResponse>(response);
    expect(body).toMatchSchema('login');
    expect(body.user).toMatchObject({ email: env.customerEmail, role: 'customer' });
    expect(new Date(body.expires_at).getTime()).toBeGreaterThan(Date.now());
  });

  test('wrong password and unknown email produce the same error', async ({ api }) => {
    const wrongPassword = await api.login(env.customerEmail, 'definitely-wrong');
    const unknownEmail = await api.login('nobody@qa-commerce.test', env.customerPassword);
    await expect(wrongPassword).toBeApiError(401, 'INVALID_CREDENTIALS');
    await expect(unknownEmail).toBeApiError(401, 'INVALID_CREDENTIALS');
    expect((await wrongPassword.json()).error.message).toBe((await unknownEmail.json()).error.message);
  });

  for (const [name, body] of [
    ['missing password', { email: env.customerEmail }],
    ['malformed email', { email: 'not-an-email', password: 'x' }],
    ['empty body', {}],
    ['unexpected field', { email: env.customerEmail, password: 'x', remember_me: true }],
  ] as const) {
    test(`login rejects ${name} with 422`, async ({ api }) => {
      const response = await api.send('POST', '/api/v1/auth/login', body);
      await expect(response).toBeApiError(422, 'VALIDATION_ERROR');
    });
  }

  test('protected endpoint without credentials returns 401 with WWW-Authenticate', async ({ api }) => {
    const response = await api.listOrders();
    await expect(response).toBeApiError(401, 'AUTHENTICATION_REQUIRED');
    expect(response.headers()['www-authenticate']).toBe('Bearer');
  });

  test('forged token is rejected', async ({ api }) => {
    const response = await api.as('forged-token-value').listOrders();
    await expect(response).toBeApiError(401, 'INVALID_TOKEN');
  });

  test('logout revokes the token immediately', async ({ customer }) => {
    await expect(await customer.api.me()).toHaveStatus(200);
    await expect(await customer.api.logout()).toHaveStatus(204);
    await expect(await customer.api.me()).toBeApiError(401, 'INVALID_TOKEN');
  });

  test('responses never expose password hashes', async ({ customer }) => {
    const text = await (await customer.api.me()).text();
    expect(text).not.toContain('argon2');
    expect(text).not.toContain('password');
  });

  test('customer cannot call admin-only endpoints', async ({ customer }) => {
    const response = await customer.api.createUser({
      email: 'x@qa-commerce.test',
      full_name: 'X',
      password: 'long-enough-password',
    });
    await expect(response).toBeApiError(403, 'FORBIDDEN');
  });
});
