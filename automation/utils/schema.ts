import fs from 'node:fs';
import path from 'node:path';
import Ajv2020, { type ErrorObject, type ValidateFunction } from 'ajv/dist/2020';
import addFormats from 'ajv-formats';

/**
 * Consumer-side JSON Schemas (automation/schemas). They are hand-written on purpose: they encode
 * what the *client* relies on, so an accidental server-side contract change fails the suite even
 * if the server's own OpenAPI document changed along with it.
 */
export type SchemaName =
  'error' | 'health' | 'inventory' | 'login' | 'money' | 'order' | 'order-page' | 'product' | 'product-page' | 'user';

const SCHEMA_DIR = path.resolve(__dirname, '..', 'schemas');

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
for (const file of fs.readdirSync(SCHEMA_DIR).filter((f) => f.endsWith('.schema.json'))) {
  ajv.addSchema(JSON.parse(fs.readFileSync(path.join(SCHEMA_DIR, file), 'utf8')));
}

function validator(name: SchemaName): ValidateFunction {
  const validate = ajv.getSchema(`${name}.schema.json`);
  if (!validate) throw new Error(`Unknown schema "${name}" (looked in ${SCHEMA_DIR})`);
  return validate;
}

export function formatErrors(errors: ErrorObject[] | null | undefined): string {
  return (errors ?? [])
    .map((e) => `  - ${e.instancePath || '(root)'} ${e.message}${e.params ? ` ${JSON.stringify(e.params)}` : ''}`)
    .join('\n');
}

export function validateSchema(name: SchemaName, data: unknown): { valid: boolean; errors: string } {
  const validate = validator(name);
  const valid = validate(data) as boolean;
  return { valid, errors: valid ? '' : formatErrors(validate.errors) };
}
