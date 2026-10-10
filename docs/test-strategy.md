# Test strategy

## Scope

**In scope:** authentication and authorisation, catalogue and inventory, order placement,
retrieval, history and cancellation, the REST contract, the web UI's main journeys, data integrity
under failure and concurrency, and test-environment hygiene.

**Out of scope (documented limitations):** performance and load, security penetration testing,
accessibility audits beyond semantic markup and label-based selectors, visual regression, mobile
browsers, payments, tax, shipping and multi-currency, which the application does not implement.

## Risk-based priorities

| Risk | Impact | Likelihood | Primary mitigation (tests) |
|---|---|---|---|
| Overselling under concurrent orders | High: promised stock that doesn't exist | Medium | Thread- and HTTP-level race tests (`TestConcurrency`, `concurrency.spec.ts`), repeated nightly |
| Partial writes when a request fails midway | High: corrupted stock or orphan orders | Medium | Fault injection at two points with API and DB assertions (`atomicity.spec.ts`, integration) |
| Incorrect money arithmetic | High: financial error | Medium | Unit tests on `rules.py`; decimal regression cases that break binary floats |
| Rejected order leaves side effects | High | Medium | Every rejection type asserts unchanged inventory and zero orders |
| Duplicate orders from retries or double-clicks | Medium | High | Idempotency tests: sequential, concurrent, UI form replay |
| Access to another customer's data | High | Low | Cross-customer 404 checks (API and UI); admin-only 403 checks |
| Contract drift breaking clients | Medium | Medium | Consumer-side JSON Schemas, OpenAPI path inventory, strict request validation tests |
| Credentials leaking into logs or artifacts | Medium | Medium | Redacted HTTP exchange log; traces disabled for API projects; 500s carry no internals |
| Flaky tests eroding trust | Medium | Medium | No retries; isolated data per test; nightly `--repeat-each` on concurrency tests |

## Test levels

| Level | Tool | Location | What it proves | Runs in |
|---|---|---|---|---|
| Unit | pytest | `backend-tests/unit` | Pure rules, schemas, error mapping, security helpers, config guards. No I/O. | PR, nightly |
| Integration | pytest + TestClient + PostgreSQL | `backend-tests/integration` | API plus real database: persistence, rollback, constraints, locking, idempotency | PR, nightly |
| API | Playwright `APIRequestContext` | `automation/tests/api` | Black-box contract: status, headers, bodies, schemas, state after failures | PR, nightly |
| Regression | Playwright | `automation/tests/regression` | Boundaries, decimals, idempotency, atomicity, real HTTP concurrency | PR, nightly (concurrency ×10) |
| UI | Playwright + Page Objects | `automation/tests/ui` | Login, catalogue, ordering, validation messages, history, access control | PR (Chromium); nightly (Chromium, Firefox, WebKit) |
| End-to-end | Playwright + read-only SQL | `automation/tests/e2e` | Cross-channel workflows: API→UI→DB and UI→API→DB | PR, nightly |
| Defect lab | `scripts/defect_lab.py` | `app/defects.py` | The suites **detect** realistic defects; controls pass on the correct code | Nightly, on demand |

Why the integration and API levels overlap: the pytest integration tests are the fast, white-box
safety net (they can assert rows directly and call services from threads). The Playwright API
tests are black-box contract tests against the running deployable, which is how a client sees it.

## Test design techniques

- **Boundary value analysis:** quantity 0/1/1000/1001/2³¹; price 0.00/0.01/999999.99/1000000.00; inventory equal to the quantity.
- **Equivalence partitioning:** wrong types (string, float, boolean, null) for strict integer fields; malformed JSON.
- **State verification after negative tests:** every rejection asserts inventory and order count are unchanged, through the API and in the database.
- **Error guessing from real-world failures:** double submission, lost updates, float rounding, open redirects, timing-based account enumeration.
- **Rule precedence:** unknown → inactive → insufficient is asserted explicitly.

## Selector and UI policy

Role and label selectors first (`getByRole`, `getByLabel`). `data-testid` only where semantics
aren't enough: table rows keyed by SKU or order id, and specific values on the detail page. Page
Objects wrap pages that are used by several specs. Assertions use Playwright's auto-waiting
`expect`; the suite contains no fixed sleeps.

## Entry and exit criteria

**Entry:** `/api/v1/health` reports ready, and the seeded admin can log in (checked by the Playwright global setup, which fails fast with an actionable message).

**Exit (PR gate):** lint, format and type checks pass; all unit, integration, API, regression, UI (Chromium) and e2e tests pass. Any failure fails the required check.

## Flakiness and retry policy

- `retries: 0` in every environment. A retry that passes hides a real defect, so there are no retries.
- Every test creates its own products and customer; nothing depends on execution order, and workers run fully in parallel.
- The nightly workflow repeats the `@concurrency` tests (default 10×) to surface intermittent races. A failure there is treated as a bug.
- Diagnostics on failure: screenshot, video and trace for browser tests; a redacted HTTP exchange log for every test; the JUnit/JSON/HTML reports.

## Diagnostics and secrets

- `api-exchanges.json` is attached to every failing test. It records method, URL, headers, bodies and status, with `password`, `access_token`, `Authorization`, cookies and CSRF tokens replaced by `[REDACTED]`.
- Playwright traces are **off** for the API and regression projects, because traces record raw `Authorization` headers.
- Browser traces (UI/e2e) can contain the synthetic test accounts' session cookies and typed passwords. That's acceptable for this local-only lab with synthetic credentials. Don't point the suite at an environment with real accounts without disabling traces.
- Application logs contain method, path, status, timing and request id only.

## Coverage notes

Backend line coverage from pytest is measured in the nightly workflow (`--cov=app`). In the local
run used for this documentation, pytest covered 86% of `app/` lines. The main gap is
`app/web/routes.py`, which the Playwright UI suites exercise but pytest doesn't measure. This figure
comes from a real run and will change as the code changes; treat the CI artifact as the source of truth.
