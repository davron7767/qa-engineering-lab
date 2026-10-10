# Troubleshooting

## Environment

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker: command not found` / Compose errors | Docker Desktop not installed or not running | Install and start Docker Desktop (needs WSL 2). Or use the Docker-free path: `.\scripts\local-postgres.ps1 start` then `.\scripts\local-app.ps1 start`. |
| `port is already allocated` for 5433 or 8000 | Another PostgreSQL or app is using the port | Set `POSTGRES_HOST_PORT` / `APP_HOST_PORT` in `.env` and update `DATABASE_URL`, `TEST_DATABASE_URL`, `BASE_URL`, `AUTOMATION_DATABASE_URL` to match |
| `/api/v1/health` returns 503 | App is up but the database is unreachable | `docker compose ps` (is `db` healthy?) or `.\scripts\local-postgres.ps1 status`. Check `DATABASE_URL`. |
| App container restarts | Migration or config error at start | `docker compose logs app`. A `SECRET_KEY must be changed` error means `APP_ENV=production` with the placeholder secret. |
| `qa_commerce_test` does not exist (Docker) | The volume was created before the init script existed | `docker compose down --volumes` and start again (the init SQL runs only on a fresh volume) |
| PowerShell refuses to run scripts | Execution policy | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or `powershell -ExecutionPolicy Bypass -File .\scripts\<script>.ps1` |
| `local-postgres.ps1 start` is slow the first time | Downloads ~330 MB of PostgreSQL binaries | Wait once; later starts take seconds |

## Test failures

| Symptom | Likely cause | Fix |
|---|---|---|
| Playwright global setup: "QA Commerce is not ready" | App not running at `BASE_URL` | Start the app, or set `BASE_URL` |
| Global setup: "Seeded admin login failed" | `SEED_ADMIN_PASSWORD` differs between the app and the test shell, or seeding is disabled | Use the same `.env` values; make sure `SEED_ON_STARTUP=true`. The seed doesn't change an existing user's password, so run `docker compose down --volumes` if you changed it after the first start. |
| `atomicity.spec.ts` fails with status 201 instead of 500 | Server started with `ENABLE_TEST_HOOKS=false` | Enable it for the lab environment (default in `.env.example` and Compose) |
| DB probe errors (`ECONNREFUSED`, auth failed) in e2e or regression tests | `AUTOMATION_DATABASE_URL` doesn't point at the app's database | Default: `postgresql://qa_commerce:qa_commerce_local@localhost:5433/qa_commerce` |
| pytest: "TEST_DATABASE_URL is not set" | Missing `.env` or variable | `Copy-Item .env.example .env` |
| pytest: "Refusing to reset database" | `TEST_DATABASE_URL` points at a database not ending in `_test` | Intentional safeguard. Point it at `qa_commerce_test`. |
| Browser tests: "Executable doesn't exist" | Playwright browsers not installed | `cd automation; npx playwright install chromium` (add `firefox webkit` for the nightly set) |

## Investigating a failed test

1. **Open the HTML report:** `cd automation; npx playwright show-report`. Each failed test shows the
   assertion diff, the source line and its attachments.
2. **Read `api-exchanges.json`** (attached to every failing test). It's the full HTTP conversation
   with secrets redacted, so you can see which request returned what. Match the `x-request-id`
   response header against the application log to find the server-side entry.
3. **Browser tests: open the trace**, either from the report or with
   `npx playwright show-trace test-results\artifacts\<test-folder>\trace.zip`. You can step through
   actions, DOM snapshots, console output and network calls. Screenshots and video sit next to it.
4. **Reproduce locally:** run just that test, e.g.
   `npx playwright test tests/api/orders.spec.ts -g "one short line" --project=api`, or watch a UI
   test with `--headed` / `--debug` / `--ui`.
5. **Backend tests:** `pytest backend-tests/integration/test_orders_api.py -k partial -vv`.
6. **CI failures:** download the `playwright-report` and `test-results-and-logs` artifacts from the
   workflow run. `reports/compose-logs.txt` contains the application and database logs.

## Resetting state

See [test-data.md](test-data.md#resetting). In short: `.\scripts\reset-test-db.ps1` for the
backend test database; `docker compose down --volumes` (or `local-postgres.ps1 destroy`) for the
development database.
