"""Defect laboratory runner: prove the test suites catch real defects.

For each selected defect it:
  1. (optional, --with-control) runs the targeted tests against the CORRECT code -> must pass;
  2. runs the targeted backend tests with DEFECT_MODE set -> must FAIL;
  3. starts a separate, temporary app instance on --port (default 8001) with DEFECT_MODE set,
     runs the targeted Playwright tests against it -> must FAIL, then stops that instance.

The normal application (port 8000) and its reports are never touched. Requires PostgreSQL to be
running (docker compose or scripts/local-postgres.ps1) and the Python/npm dependencies installed.

Usage:
    python scripts/defect_lab.py --list
    python scripts/defect_lab.py wrong_total
    python scripts/defect_lab.py --all --with-control
    python scripts/defect_lab.py oversell_race --suite playwright
Exit code 0 only if every selected defect was detected by every selected suite.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "automation"
LOG_DIR = ROOT / "reports" / "defect-lab"


@dataclass(frozen=True)
class Defect:
    summary: str
    pytest_targets: tuple[str, ...]
    playwright_files: tuple[str, ...]
    playwright_grep: str


DEFECTS: dict[str, Defect] = {
    "wrong_total": Defect(
        "Line totals use binary floats truncated to cents (0.29 x 3 = 0.86)",
        ("backend-tests/integration/test_orders_api.py::TestPlaceOrder",),
        ("tests/regression/boundaries.spec.ts",),
        "Decimal currency calculations",
    ),
    "inventory_before_validation": Defect(
        "Stock is reserved and committed before the whole order is validated",
        ("backend-tests/integration/test_orders_api.py::TestRejectedOrdersLeaveNoTrace",),
        ("tests/api/orders.spec.ts",),
        "one short line rejects the whole multi-line order",
    ),
    "persist_rejected_order": Defect(
        "The order row is committed before validation, so rejected orders persist",
        ("backend-tests/integration/test_orders_api.py::TestRejectedOrdersLeaveNoTrace",),
        ("tests/api/orders.spec.ts", "tests/regression/atomicity.spec.ts"),
        "leave state unchanged|Failure after partial processing",
    ),
    "oversell_race": Defect(
        "Inventory is read and written without row locks (lost update)",
        ("backend-tests/integration/test_orders_api.py::TestConcurrency",),
        ("tests/regression/concurrency.spec.ts",),
        "Concurrent orders",
    ),
}


def run(cmd: list[str], env: dict[str, str], cwd: Path, log_name: str) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / log_name
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(cmd, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)  # noqa: S603
    tail = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-3:]
    print("      " + "\n      ".join(tail))
    print(f"      full log: {log_path.relative_to(ROOT)}")
    return result.returncode


def base_env(defect: str | None) -> dict[str, str]:
    env = dict(os.environ)
    env["DEFECT_MODE"] = defect or ""
    env["ENABLE_TEST_HOOKS"] = "true"
    return env


def pytest_cmd(defect: Defect) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:warnings",
        "--no-header",
        *defect.pytest_targets,
    ]


def playwright_cmd(defect: Defect) -> list[str]:
    npx = shutil.which("npx") or "npx"
    return [
        npx,
        "playwright",
        "test",
        "--project=api",
        "--project=regression",
        *defect.playwright_files,
        "--grep",
        defect.playwright_grep,
    ]


def wait_ready(url: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310 - local URL
                if response.status == 200:
                    return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"defect-mode app did not become ready at {url}")


def run_playwright(name: str, defect: Defect, port: int, with_defect: bool) -> int:
    env = base_env(name if with_defect else None)
    label = name if with_defect else f"{name}-control"
    server = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "app.serve", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=(LOG_DIR / f"{label}-server.log").open("w"),
    )
    try:
        wait_ready(f"http://127.0.0.1:{port}/api/v1/health")
        pw_env = dict(
            env,
            BASE_URL=f"http://localhost:{port}",
            PW_REPORT_DIR=f"defect-lab-report/{label}",
            PW_RESULTS_DIR=f"defect-lab-results/{label}",
        )
        return run(playwright_cmd(defect), pw_env, AUTOMATION, f"{label}-playwright.log")
    finally:
        server.terminate()
        server.wait(timeout=15)


def evaluate(name: str, suites: set[str], port: int, with_control: bool) -> bool:
    defect = DEFECTS[name]
    print(f"\n=== {name}: {defect.summary}")
    ok = True
    if "backend" in suites:
        if with_control:
            print("   [control] backend tests on correct code (expect PASS)")
            ok &= run(pytest_cmd(defect), base_env(None), ROOT, f"{name}-control-backend.log") == 0
        print("   [defect]  backend tests with defect (expect FAIL)")
        detected = run(pytest_cmd(defect), base_env(name), ROOT, f"{name}-backend.log") != 0
        print(f"   backend: {'DETECTED' if detected else 'NOT DETECTED'}")
        ok &= detected
    if "playwright" in suites:
        if with_control:
            print("   [control] Playwright tests on correct code (expect PASS)")
            ok &= run_playwright(name, defect, port, with_defect=False) == 0
        print("   [defect]  Playwright tests with defect (expect FAIL)")
        detected = run_playwright(name, defect, port, with_defect=True) != 0
        print(f"   playwright: {'DETECTED' if detected else 'NOT DETECTED'}")
        ok &= detected
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the defect laboratory")
    parser.add_argument("defects", nargs="*", metavar="DEFECT", help=", ".join(DEFECTS))
    parser.add_argument("--all", action="store_true", help="run every defect")
    parser.add_argument("--list", action="store_true", help="list defects and exit")
    parser.add_argument("--suite", choices=["backend", "playwright", "all"], default="all")
    parser.add_argument(
        "--with-control",
        action="store_true",
        help="first require the same tests to pass on the correct code",
    )
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.list:
        for name, defect in DEFECTS.items():
            print(f"{name:30} {defect.summary}")
        return 0
    selected = list(DEFECTS) if args.all else args.defects
    if not selected:
        parser.error("name at least one defect, or pass --all / --list")
    unknown = [name for name in selected if name not in DEFECTS]
    if unknown:
        parser.error(f"unknown defect(s): {', '.join(unknown)} (see --list)")

    suites = {"backend", "playwright"} if args.suite == "all" else {args.suite}
    results = {name: evaluate(name, suites, args.port, args.with_control) for name in selected}

    print("\n=== Defect lab summary")
    for name, ok in results.items():
        print(
            f"   {name:30} {'PASS (detected)' if ok else 'FAIL (not detected or control failed)'}"
        )
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
