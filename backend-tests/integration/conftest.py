"""Integration fixtures: a real PostgreSQL *_test database, reset to seed state before every test.

The app under test is pointed at TEST_DATABASE_URL by overriding DATABASE_URL *before* any
settings or engine are created. The reset helpers refuse to touch non-"_test" databases.
"""

import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from support import ADMIN, CUSTOMER, CUSTOMER2, login

from app.config import get_settings
from app.db.reset import assert_test_database, reset_test_database, restore_seed_state
from app.db.session import get_engine, get_session_factory


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or get_settings().test_database_url
    if not url:
        pytest.exit("TEST_DATABASE_URL is not set (see .env.example)", returncode=2)
    assert_test_database(url)
    return url


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = _test_database_url()
    os.environ["DATABASE_URL"] = url
    os.environ["ENABLE_TEST_HOOKS"] = "true"
    os.environ["SEED_ADMIN_PASSWORD"] = ADMIN[1]
    os.environ["SEED_CUSTOMER_PASSWORD"] = CUSTOMER[1]
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    reset_test_database(url)  # migrations + truncate + full seed, once per run
    yield url
    get_engine().dispose()


@pytest.fixture(autouse=True)
def clean_state(database_url: str) -> None:
    restore_seed_state(database_url)


@pytest.fixture(scope="session")
def app(database_url: str) -> Any:
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def lenient_client(app: Any) -> Iterator[TestClient]:
    """Returns 500 responses instead of re-raising, for tests that provoke server errors."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def db() -> Iterator[Session]:
    """A separate session for asserting persisted state (never shares the app's session)."""
    with get_session_factory()() as session:
        yield session


@pytest.fixture
def customer_headers(client: TestClient) -> dict[str, str]:
    return login(client, *CUSTOMER)


@pytest.fixture
def customer2_headers(client: TestClient) -> dict[str, str]:
    return login(client, *CUSTOMER2)


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    return login(client, *ADMIN)


@pytest.fixture
def make_product(client: TestClient, admin_headers: dict[str, str]) -> Callable[..., dict]:
    counter = iter(range(1, 10_000))

    def _make(price: str = "10.00", inventory: int = 10, is_active: bool = True) -> dict:
        body = {
            "sku": f"IT-{next(counter):04d}",
            "name": "Integration test product",
            "price": price,
            "inventory": inventory,
            "is_active": is_active,
        }
        response = client.post("/api/v1/products", json=body, headers=admin_headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
