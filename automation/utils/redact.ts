/**
 * Redaction for diagnostics. Anything attached to a test report passes through here, so
 * passwords and bearer tokens never end up in HTML reports or CI artifacts.
 */
const SENSITIVE_KEYS = /^(password|access_token|token|authorization|cookie|set-cookie|csrf_token)$/i;
const BEARER = /Bearer\s+[A-Za-z0-9._~+/-]+=*/g;

export function redact(value: unknown): unknown {
  if (typeof value === 'string') return value.replace(BEARER, 'Bearer [REDACTED]');
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, inner]) => [
        key,
        SENSITIVE_KEYS.test(key) ? '[REDACTED]' : redact(inner),
      ]),
    );
  }
  return value;
}
