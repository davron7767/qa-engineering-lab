# Defect laboratory

The defect lab shows that the automated suites catch realistic defects, not just that they pass.

## How it works

- `app/defects.py` contains four deliberately broken implementations. They are loaded **only** when
  `DEFECT_MODE=<name>` is set, and the application refuses to start with `DEFECT_MODE` when
  `APP_ENV=production`. The normal code has no bug branches.
- `scripts/defect_lab.py` runs, for each defect:
  1. **control** (with `--with-control`): the targeted tests against the correct code, which must **pass**;
  2. **backend**: the targeted pytest integration tests in-process with `DEFECT_MODE` set, which must **fail**;
  3. **Playwright**: a temporary app on port **8001** with `DEFECT_MODE` set, the targeted Playwright tests against it, which must **fail**. The temporary app is then stopped.
- The normal application on port 8000 and the normal reports are never touched. Logs go to
  `reports/defect-lab/`; Playwright reports go to `automation/defect-lab-report/<defect>/`.
- The nightly workflow runs `--all --with-control`; the job fails if any defect goes undetected.

## Reproduce

Prerequisites: PostgreSQL running (`docker compose up -d` or `.\scripts\local-postgres.ps1 start`),
Python virtualenv and `automation` npm dependencies installed.

```powershell
.\.venv\Scripts\python.exe scripts\defect_lab.py --list
.\.venv\Scripts\python.exe scripts\defect_lab.py wrong_total
.\.venv\Scripts\python.exe scripts\defect_lab.py --all --with-control
# Inspect a detected failure:
cd automation; npx playwright show-report defect-lab-report\inventory_before_validation
```

To explore a defect by hand, start a defect-mode instance on its own port:

```powershell
.\scripts\local-app.ps1 start -Port 8001 -Env @{ DEFECT_MODE = 'wrong_total' }
# ...use http://localhost:8001 ...
.\scripts\local-app.ps1 stop -Port 8001
```

## The defects

### 1. `wrong_total`: money computed with binary floats

| | |
|---|---|
| **Defect** | `line_total` computes `int(float(price) * qty * 100) / 100`, i.e. binary floating point and truncation |
| **Business impact** | Customers are under-charged by a cent on some lines (0.29 × 3 → 0.86). It's systematic, so revenue and accounting don't reconcile. |
| **Expected behaviour** | `Decimal` arithmetic: 0.29 × 3 = **0.87**, 1.15 × 7 = **8.05** |
| **Detected by (backend)** | `test_orders_api.py::TestPlaceOrder::test_success_persists_order_lines_and_decrements_inventory` (expects total `60.85`) |
| **Detected by (Playwright)** | `regression/boundaries.spec.ts` › *Decimal currency calculations*: `total for 0.29 x 3 is exact`, `total for 1.15 x 7 is exact` |
| **Prevents recurrence** | The regression cases are values for which binary floats are wrong, so any future float shortcut fails immediately. Unit tests on `rules.py` also reject float inputs outright. |

### 2. `inventory_before_validation`: stock reserved before the order is validated

| | |
|---|---|
| **Defect** | Each line's stock is "reserved" and **committed** before the whole order is validated. A later invalid line rejects the order but keeps the earlier reservations. |
| **Business impact** | Phantom stock loss: products show as sold out although nothing was sold, which means lost sales and inventory that doesn't match the warehouse. |
| **Expected behaviour** | A rejected multi-line order changes no inventory at all (single transaction) |
| **Detected by (backend)** | `TestRejectedOrdersLeaveNoTrace::test_rejection_has_no_side_effects[partial-multi-line]`, `…test_failure_mid_transaction_rolls_back_everything[after_inventory_decrement]`, `[after_order_insert]` |
| **Detected by (Playwright)** | `api/orders.spec.ts` › *one short line rejects the whole multi-line order* (expected 100, received 95; see the README screenshot) |
| **Prevents recurrence** | Every rejection test asserts unchanged inventory for **all** lines, not only the failing one, and the fault-injection tests prove rollback after the decrement step. |

### 3. `persist_rejected_order`: order row committed before validation

| | |
|---|---|
| **Defect** | The order header is committed first "to obtain an id", then validated. Rejections leave empty `confirmed` orders with total 0.00. |
| **Business impact** | Customers see phantom orders in their history; fulfilment and reporting count orders that don't exist. |
| **Expected behaviour** | A rejected order leaves no order row; history is unchanged |
| **Detected by (backend)** | All 5 `test_rejection_has_no_side_effects[...]` cases that reach business validation (over-stock, out-of-stock, inactive, unknown, partial multi-line), plus both fault-injection cases |
| **Detected by (Playwright)** | `api/orders.spec.ts` › *insufficient inventory: 409 with details, nothing decremented* (history must be empty), and `regression/atomicity.spec.ts` › both fault cases (database probe finds orphan rows) |
| **Prevents recurrence** | Negative tests always check the **order count** as well as the status code, so "correct error, wrong side effects" can't pass. |

### 4. `oversell_race`: read-modify-write without row locks

| | |
|---|---|
| **Defect** | Inventory is read with a plain `SELECT` (no `FOR UPDATE`) and written back as an absolute value after a short delay standing in for real work (e.g. a payment call) |
| **Business impact** | Under load, several customers buy the last unit; stock goes wrong (lost updates) and orders can't be fulfilled. |
| **Expected behaviour** | With 1 unit and 10 concurrent buyers, exactly 1 order succeeds and 9 get `409 INSUFFICIENT_INVENTORY` |
| **Detected by (backend)** | `TestConcurrency::test_last_unit_sold_exactly_once`, `…test_concurrent_partial_stock_never_oversells`, `…test_concurrent_duplicate_submissions_create_one_order` |
| **Detected by (Playwright)** | `regression/concurrency.spec.ts`: all three tests (real parallel HTTP requests) |
| **Prevents recurrence** | Concurrency tests use barriers or `Promise.all` to maximise overlap. The nightly workflow repeats them 10× so intermittent races surface. |

## Results from the most recent local run

`python scripts/defect_lab.py --all --with-control`: every control run passed, and every defect was
**detected by both suites**. The exact failing tests are listed in the tables above, taken from that
run's logs. Re-run the command to reproduce; nothing here is estimated.
