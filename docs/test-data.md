# Test data and cleanup strategy

All data is synthetic. Accounts use the reserved `.test` top-level domain, and passwords are
local-only placeholders configured in `.env`.

## Deterministic seed (`app/db/seed.py`)

Inserted on startup when `SEED_ON_STARTUP=true`, keyed by natural keys (e-mail, SKU) and idempotent.
Re-running inserts only what's missing and never overwrites existing rows.

| Account | Role | Customer ref | Password variable |
|---|---|---|---|
| `admin@qa-commerce.test` | admin | CUST-000001 | `SEED_ADMIN_PASSWORD` (default `Admin#Local2024`) |
| `customer@qa-commerce.test` | customer | CUST-000002 | `SEED_CUSTOMER_PASSWORD` (default `Customer#Local2024`) |
| `customer2@qa-commerce.test` | customer | CUST-000003 | `SEED_CUSTOMER_PASSWORD` |

| SKU | Name | Price | Stock | Purpose |
|---|---|---:|---:|---|
| QA-KB-001 | Mechanical Keyboard | 89.99 | 25 | Normal product |
| QA-MS-002 | Wireless Mouse | 29.99 | 50 | Normal product |
| QA-MN-003 | 27-inch Monitor | 249.00 | 3 | Low stock |
| QA-HB-004 | USB-C Hub | 39.95 | 0 | Out of stock |
| QA-CT-005 | Cable Ties (10 pack) | 0.29 | 1000 | Float-unfriendly price |
| QA-WC-006 | HD Webcam | 59.50 | 10 | Normal product |
| QA-LS-007 | Laptop Stand (Discontinued) | 45.00 | 12 | **Inactive** |

On a freshly reset database the seed products get ids 1–7. The backend integration tests rely on
that (they reset before every test). Playwright tests **never** rely on numeric ids for seed data:
they look products up by SKU, and they **never mutate seed records**.

## Isolation rules

| Suite | Strategy | Why |
|---|---|---|
| Backend integration | Dedicated `qa_commerce_test` database. Full reset (migrate, truncate, seed) once per session, then a fast reset before **every** test (truncate orders, sessions and products; drop non-seed users; re-seed). | Deterministic ids and exact counts; tests can assert the absolute DB state |
| Playwright (all projects) | Runs against the live application database. Every test creates **its own** products (unique SKU) and **its own** customer through the admin API (`testData` / `customer` fixtures). | Parallel-safe and repeatable without resetting a database another process is using |

Unique values come from `automation/data/factories.ts`: a per-run id plus random bytes, e.g. SKU
`PW-MV2QSDXH-F87EE1` and e-mail `pw-mv2qsdxh-f87ee1@qa-commerce.test`. That means:

- parallel workers cannot collide;
- repeated runs never conflict with earlier runs' data;
- data from a specific run can be recognised when debugging.

## Cleanup

- **Playwright:** products created by a test are **retired** (`is_active=false`) at fixture
  teardown. They can't be deleted because orders reference them. Created customers and their orders
  remain as an audit trail. None of this affects later runs, because every assertion targets the
  test's own records.
- **Backend integration:** wiped before every test, so nothing accumulates.
- **Development database:** grows with each Playwright run. Reset it whenever you like (see below).

## Resetting

| Target | Command | Safety |
|---|---|---|
| Backend test database | `.\scripts\reset-test-db.ps1` (or `python -m app.db.reset`) | Refuses any database whose name doesn't end in `_test` |
| Development database (Docker) | `docker compose down --volumes` then `docker compose up -d` | Removes **only** this Compose project's `pgdata` volume (project name `qa-engineering-lab`) |
| Development database (portable PostgreSQL) | `.\scripts\local-postgres.ps1 destroy` then `start` | Deletes only `.local\pgdata` inside this repository |

## Choosing a setup technique

| Technique | Use when | Example in this repo |
|---|---|---|
| **API setup** (default for black-box suites) | You need realistic records quickly and the API can create them. Fast, goes through real validation, works against any environment. | `testData.createProduct()`, `testData.createCustomer()` |
| **Database fixtures** | White-box tests that need a known absolute state, or states the API can't produce (expired sessions, constraint violations) | Integration `clean_state` fixture; expiring a session with SQL in `test_auth_api.py` |
| **UI setup** | Only when the UI journey itself is under test. It's slow and brittle as setup. | `ui-to-api.spec.ts` logs in through the form because that *is* the behaviour under test |
| **Session injection** | UI tests that need a signed-in user but aren't testing login | `customerPage` fixture adds the API session token as the `qa_session` cookie |

Read-only database checks (`automation/utils/db.ts`) verify persisted state behind the API. Every
connection runs with `default_transaction_read_only=on`, so a mistaken query cannot modify data.
