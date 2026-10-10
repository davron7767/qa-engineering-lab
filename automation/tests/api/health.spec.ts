import { test, expect, json } from '../../fixtures/test';

test.describe('Health and API documentation', { tag: '@smoke' }, () => {
  test('readiness reports database ok', async ({ api }) => {
    const response = await api.send('GET', '/api/v1/health');
    await expect(response).toHaveStatus(200);
    const body = await json(response);
    expect(body).toMatchSchema('health');
    expect(body).toMatchObject({ status: 'ok', database: 'ok' });
  });

  test('liveness does not depend on the database', async ({ api }) => {
    const response = await api.send('GET', '/api/v1/health/live');
    await expect(response).toHaveStatus(200);
    expect(await response.json()).toEqual({ status: 'ok' });
  });

  test('echoes a caller-supplied X-Request-ID for log correlation', async ({ api }) => {
    const response = await api.send('GET', '/api/v1/health/live', undefined, {
      headers: { 'X-Request-ID': 'pw-correlation-123' },
    });
    expect(response.headers()['x-request-id']).toBe('pw-correlation-123');
  });

  test('generates a request id when none is supplied', async ({ api }) => {
    const response = await api.send('GET', '/api/v1/health/live');
    expect(response.headers()['x-request-id']).toMatch(/^[0-9a-f]{32}$/);
  });

  test('serves the OpenAPI document with every documented endpoint', async ({ api }) => {
    const response = await api.send('GET', '/openapi.json');
    await expect(response).toHaveStatus(200);
    const spec = await response.json();
    expect(Object.keys(spec.paths).sort()).toEqual(
      [
        '/api/v1/auth/login',
        '/api/v1/auth/logout',
        '/api/v1/auth/me',
        '/api/v1/health',
        '/api/v1/health/live',
        '/api/v1/orders',
        '/api/v1/orders/{order_id}',
        '/api/v1/orders/{order_id}/cancel',
        '/api/v1/products',
        '/api/v1/products/{product_id}',
        '/api/v1/products/{product_id}/inventory',
        '/api/v1/users',
      ].sort(),
    );
  });
});
