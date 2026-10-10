"""Reset a TEST database to the deterministic seed state.

Safety: refuses any database whose name does not end in "_test". It truncates the project's
own tables only; it never drops databases, roles or Docker volumes.

Usage:
    python -m app.db.reset                       # uses TEST_DATABASE_URL
    python -m app.db.reset --database-url <url>  # explicit *_test database
"""

import argparse

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.migrate import upgrade_to_head
from app.db.seed import seed


class UnsafeResetError(RuntimeError):
    pass


def assert_test_database(database_url: str) -> None:
    name = make_url(database_url).database or ""
    if not name.endswith("_test"):
        raise UnsafeResetError(
            f"Refusing to reset database '{name}': only databases ending in '_test' may be reset."
        )


def truncate_all(database_url: str) -> None:
    assert_test_database(database_url)
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    finally:
        engine.dispose()


def restore_seed_state(database_url: str) -> None:
    """Fast per-test reset: wipe orders, sessions and products, drop non-seed users, re-seed.
    Seed users are kept, which avoids re-hashing their passwords for every test."""
    from app.db.seed import SEED_USERS

    assert_test_database(database_url)
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "TRUNCATE order_items, orders, auth_sessions, products RESTART IDENTITY CASCADE"
                )
            )
            conn.execute(
                text("DELETE FROM users WHERE email <> ALL(:emails)"),
                {"emails": [u.email for u in SEED_USERS]},
            )
        seed(sessionmaker(bind=engine))
    finally:
        engine.dispose()


def reset_test_database(database_url: str) -> dict[str, int]:
    assert_test_database(database_url)
    upgrade_to_head(database_url)
    truncate_all(database_url)
    engine = create_engine(database_url)
    try:
        return seed(sessionmaker(bind=engine))
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    from app.config import get_settings

    url = args.database_url or get_settings().test_database_url
    if not url:
        raise SystemExit("Set TEST_DATABASE_URL or pass --database-url")
    try:
        inserted = reset_test_database(url)
    except UnsafeResetError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Reset {make_url(url).database}: seeded {inserted}")


if __name__ == "__main__":
    main()
