# API contract — QA Commerce `/api/v1`

The live, machine-readable contract is served by FastAPI at **`/openapi.json`** (Swagger UI at
`/docs`, ReDoc at `/redoc`). This document explains the conventions and business rules behind it.
The consumer-side JSON Schemas in [`automation/schemas/`](../automation/schemas) enforce the parts
clients rely on.

## Conventions

| Topic | Rule |
|---|---|
| Base path | `/api/v1` |
| Content type | `application/json` for requests and responses |
| Authentication | `Authorization: Bearer <access_token>` from `POST /auth/login` |
| Money | JSON **string** with exactly two decimals, e.g. `"19.99"`. Never a JSON number. Currency is always `USD`. |
| Timestamps | ISO 8601 with UTC offset, e.g. `2026-10-10T18:21:31.395281Z` |
| Ids | Products and users: positive int32. Orders: UUID v4. |
| Unknown fields | Request bodies **reject** unknown fields (`422`), so clients cannot send `total` or `unit_price` |
| Request id | Every response has `X-Request-ID`. A caller-supplied `X-Request-ID` (1–64 chars) is echoed back. |
| Pagination | `page` (≥1, default 1) and `page_size` (1–100, default 20). Response: `{items, page, page_size, total, pages}` |

## Error envelope

Every error, including validation errors, 404s for unknown routes and unexpected 500s, uses one shape:

```json
{
  "error": {
    "code": "INSUFFICIENT_INVENTORY",
    "message": "Insufficient inventory for one or more items",
    "details": [{ "product_id": 3, "sku": "QA-MN-003", "requested": 4, "available": 3 }],
    "request_id": "cf10ab43f8aa497484ca7ac09b502b97"
  }
}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `UNKNOWN_PRODUCT` | An order line references a product id that does not exist (`details`: `[{product_id}]`) |
| 400 | `PRODUCT_INACTIVE` | An order line references an inactive product (`details`: `[{product_id, sku}]`) |
| 401 | `AUTHENTICATION_REQUIRED` | No bearer token, an empty one, or a non-Bearer scheme. Sends `WWW-Authenticate: Bearer`. |
| 401 | `INVALID_TOKEN` | Token unknown, revoked by logout, or expired |
| 401 | `INVALID_CREDENTIALS` | Login failed. Same message for wrong password and unknown e-mail. |
| 403 | `FORBIDDEN` | Authenticated customer calls an admin-only endpoint |
| 404 | `PRODUCT_NOT_FOUND` / `ORDER_NOT_FOUND` / `NOT_FOUND` | Missing resource or route. Another customer's order is also reported as `ORDER_NOT_FOUND`, so order ids cannot be probed. |
| 409 | `INSUFFICIENT_INVENTORY` | Requested quantity exceeds available stock (`details` lists **every** short line) |
| 409 | `IDEMPOTENCY_KEY_REUSED` | Same `Idempotency-Key` sent with a different body |
| 409 | `ORDER_NOT_CANCELLABLE` | Cancelling an order that is not `confirmed` |
| 409 | `SKU_ALREADY_EXISTS` / `EMAIL_ALREADY_EXISTS` | Uniqueness conflicts |
| 422 | `VALIDATION_ERROR` | Schema or parameter validation failed. `details`: `[{loc, msg, type}]` (FastAPI convention). |
| 500 | `INTERNAL_ERROR` | Unexpected failure. No exception text or stack trace is returned. Both 500 codes send `Connection: close`, because the server drops the connection after an unhandled error. |
| 500 | `INJECTED_FAULT` | Deliberate failure from the opt-in test hook (see below) |

## Endpoints

### Health

| Method | Path | Auth | Success | Notes |
|---|---|---|---|---|
| GET | `/health/live` | – | 200 `{"status":"ok"}` | Liveness. Never touches the database. |
| GET | `/health` | – | 200 `{status, database, version, environment}` | Readiness. **503** with `status: "unavailable"` if the database does not answer within ~3 s per attempt. |

### Authentication and users

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| POST | `/auth/login` | – | 200 `{access_token, token_type:"bearer", expires_at, user}` | 401, 422 |
| POST | `/auth/logout` | Bearer | 204, token revoked immediately | 401 |
| GET | `/auth/me` | Bearer | 200 `User` | 401 |
| POST | `/users` | Admin | 201 `User` | 401, 403, 409, 422 |

`LoginRequest`: `email` (string, ≤254, must look like an e-mail, case-insensitive), `password` (1–128).
`UserCreate`: `email`, `full_name` (1–120), `password` (12–128), `role` (`customer` default | `admin`).
`User`: `{id, email, full_name, role, customer_ref}`, where `customer_ref` matches `CUST-` + 6 digits.
Tokens are opaque random strings; the server stores only their SHA-256. Lifetime: `SESSION_TTL_MINUTES` (default 60).

### Products and inventory

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| GET | `/products` | – | 200 `ProductPage` | 422 |
| GET | `/products/{id}` | – | 200 `Product` | 404, 422 |
| GET | `/products/{id}/inventory` | – | 200 `Inventory` | 404, 422 |
| POST | `/products` | Admin | 201 `Product` | 401, 403, 409, 422 |
| PATCH | `/products/{id}` | Admin | 200 `Product` (name, description, price, is_active) | 401, 403, 404, 422 |
| PUT | `/products/{id}/inventory` | Admin | 200 `Inventory` | 401, 403, 404, 422 |

List filters: `search` (≤100 chars, case-insensitive substring of name, SKU or description, LIKE
wildcards escaped), `active` (bool), `in_stock` (`true` means inventory > 0, `false` means = 0),
`min_price` / `max_price` (inclusive; `min_price > max_price` gives 422). Results are ordered by id.

`ProductCreate`:

| Field | Type | Constraints |
|---|---|---|
| `sku` | string | `^[A-Z0-9][A-Z0-9-]{2,31}$`, unique |
| `name` | string | 1–120 |
| `description` | string | ≤2000, default `""` |
| `price` | number or numeric string | `0.01`–`999999.99`, at most 2 decimals, finite |
| `inventory` | integer (strict) | `0`–`1000000` |
| `is_active` | boolean | default `true` |

`Product`: the fields above plus `id`, `in_stock`, `created_at`, `updated_at`; `price` is a money string.
`Inventory`: `{product_id, sku, available, in_stock, updated_at}`. `InventoryUpdate`: `{available}` (strict int, 0–1000000).

### Orders

| Method | Path | Auth | Success | Errors |
|---|---|---|---|---|
| POST | `/orders` | Bearer | **201** `Order` + `Location` header; **200** on idempotent replay | 400, 401, 409, 422 |
| GET | `/orders` | Bearer | 200 `OrderPage` (own orders, newest first) | 401, 422 |
| GET | `/orders/{id}` | Bearer | 200 `Order` (own; admins may read any) | 401, 404, 422 |
| POST | `/orders/{id}/cancel` | Bearer | 200 `Order` with `status: "cancelled"` | 401, 404, 409, 422 |

`OrderCreate`:

```json
{ "items": [ { "product_id": 1, "quantity": 2 } ] }
```

| Field | Constraints |
|---|---|
| `items` | 1–50 lines; each `product_id` at most once |
| `items[].product_id` | strict integer, 1 – 2147483647 |
| `items[].quantity` | strict integer, 1–1000 (`"2"`, `2.0`, `true` are rejected) |

`Order`:

```json
{
  "id": "73e81206-6bbf-4af0-ab24-c21b90c842d1",
  "customer_ref": "CUST-000002",
  "status": "confirmed",
  "currency": "USD",
  "items": [
    { "product_id": 5, "sku": "QA-CT-005", "product_name": "Cable Ties (10 pack)",
      "quantity": 3, "unit_price": "0.29", "line_total": "0.87" }
  ],
  "total": "0.87",
  "created_at": "2026-10-10T18:21:31.395281Z"
}
```

## Business rules

1. **Server-side pricing.** `unit_price` is taken from the catalogue when the order is placed.
   `line_total = unit_price × quantity` and `total = Σ line_total` use `Decimal` and are rounded
   half-up to cents (with 2-decimal prices and integer quantities no rounding actually occurs). There
   is no tax, shipping or discount.
2. **Snapshots.** Order lines keep the SKU, name and unit price from the moment of purchase. Later
   catalogue changes do not alter existing orders.
3. **Validation order.** Schema validation (422) runs first. Then, under row locks: unknown product
   (400), inactive product (400), insufficient inventory (409). The first failing rule is reported.
4. **Atomicity.** Validation, inventory decrement and order insert run in one database transaction.
   Any failure rolls back everything. A rejected or failed order never changes inventory and never
   leaves an order row.
5. **No overselling.** Product rows are locked (`SELECT … FOR UPDATE`, ascending id) for the
   duration of the transaction, so concurrent orders for the last unit are serialised. Database
   `CHECK (inventory >= 0)` is a second line of defence.
6. **Idempotency.** `Idempotency-Key` is optional: 1–64 chars from `[A-Za-z0-9_-]`, scoped per user.
   - Same key and same body (compared after sorting lines) → `200`, the original order, header `Idempotent-Replayed: true`, no new side effects.
   - Same key and different body → `409 IDEMPOTENCY_KEY_REUSED`.
   - Concurrent duplicates are resolved by a unique constraint: exactly one order is created and the others replay it.
   - **Without** a key, two identical requests create two orders (intended).
   - The web UI always sends a per-form key, so a re-submitted form cannot create a duplicate.
7. **Cancellation** is allowed only for `confirmed` orders. It returns every quantity to inventory
   atomically and can happen only once.

## Opt-in test hooks

When the server runs with `ENABLE_TEST_HOOKS=true` and `APP_ENV` is not `production`, the request
header `X-Test-Fault: after_inventory_decrement | after_order_insert` makes order placement fail
mid-transaction with `500 INJECTED_FAULT`. Tests use it to prove the rollback guarantee from the
outside. Without the flag the header is ignored.

## Known contract limitations

- No product deletion (orders reference products); retire products with `is_active: false`.
- No self-registration; users are created by an admin.
- No rate limiting on login.
- Order status is either `confirmed` or `cancelled`; there is no fulfilment workflow.
