import { expect as baseExpect, type APIResponse } from '@playwright/test';
import { validateSchema, type SchemaName } from '../utils/schema';
import { redact } from '../utils/redact';

async function bodyPreview(response: APIResponse): Promise<string> {
  try {
    return JSON.stringify(redact(await response.json()), null, 2);
  } catch {
    return (await response.text()).slice(0, 1_000);
  }
}

/**
 * Domain matchers that produce actionable failure messages:
 *   await expect(response).toHaveStatus(201)        -> on failure prints method, URL and body
 *   expect(body).toMatchSchema('order')             -> on failure lists every schema violation
 *   await expect(response).toBeApiError(409, 'INSUFFICIENT_INVENTORY')
 */
export const expect = baseExpect.extend({
  async toHaveStatus(response: APIResponse, expected: number) {
    const actual = response.status();
    const pass = actual === expected;
    const body = pass ? '' : await bodyPreview(response);
    return {
      pass,
      name: 'toHaveStatus',
      expected,
      actual,
      message: () =>
        pass
          ? `expected ${response.url()} not to return HTTP ${expected}`
          : `expected HTTP ${expected} but got ${actual} from ${response.url()}\nbody: ${body}`,
    };
  },

  toMatchSchema(received: unknown, schema: SchemaName) {
    const { valid, errors } = validateSchema(schema, received);
    return {
      pass: valid,
      name: 'toMatchSchema',
      message: () =>
        valid
          ? `expected value not to match schema "${schema}"`
          : `value does not match schema "${schema}":\n${errors}\nvalue: ${JSON.stringify(redact(received), null, 2)}`,
    };
  },

  async toBeApiError(response: APIResponse, status: number, code: string) {
    const actualStatus = response.status();
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = await response.text();
    }
    const schema = validateSchema('error', body);
    const actualCode = (body as { error?: { code?: string } })?.error?.code;
    const pass = actualStatus === status && schema.valid && actualCode === code;
    return {
      pass,
      name: 'toBeApiError',
      expected: `${status} ${code}`,
      actual: `${actualStatus} ${actualCode}`,
      message: () =>
        pass
          ? `expected response not to be API error ${status} ${code}`
          : [
              `expected API error ${status} ${code} but got ${actualStatus} ${actualCode ?? '(no error code)'}`,
              schema.valid ? '' : `error envelope schema violations:\n${schema.errors}`,
              `url: ${response.url()}`,
              `body: ${JSON.stringify(redact(body), null, 2)}`,
            ]
              .filter(Boolean)
              .join('\n'),
    };
  },
});
