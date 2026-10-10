"""Error mapping: every failure leaves the API in the same documented envelope."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import errors
from app.faults import InjectedFault


@pytest.mark.parametrize(
    ("error_class", "status", "code"),
    [
        (errors.AuthenticationRequired, 401, "AUTHENTICATION_REQUIRED"),
        (errors.InvalidCredentials, 401, "INVALID_CREDENTIALS"),
        (errors.Forbidden, 403, "FORBIDDEN"),
        (errors.ProductNotFound, 404, "PRODUCT_NOT_FOUND"),
        (errors.OrderNotFound, 404, "ORDER_NOT_FOUND"),
        (errors.UnknownProduct, 400, "UNKNOWN_PRODUCT"),
        (errors.ProductInactive, 400, "PRODUCT_INACTIVE"),
        (errors.InsufficientInventory, 409, "INSUFFICIENT_INVENTORY"),
        (errors.IdempotencyKeyReused, 409, "IDEMPOTENCY_KEY_REUSED"),
        (errors.OrderNotCancellable, 409, "ORDER_NOT_CANCELLABLE"),
        (errors.DuplicateSku, 409, "SKU_ALREADY_EXISTS"),
        (errors.DuplicateEmail, 409, "EMAIL_ALREADY_EXISTS"),
    ],
)
def test_error_class_mapping(error_class: type[errors.AppError], status: int, code: str) -> None:
    assert (error_class.status_code, error_class.code) == (status, code)


class Body(BaseModel):
    quantity: int


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    errors.register_error_handlers(app)

    @app.get("/api/business")
    def business() -> None:
        raise errors.InsufficientInventory("short", [{"product_id": 1}])

    @app.get("/api/auth")
    def auth() -> None:
        raise errors.AuthenticationRequired("login please")

    @app.post("/api/validate")
    def validate(body: Body) -> None:
        return None

    @app.get("/api/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail: password=hunter2")

    @app.get("/api/fault")
    def fault() -> None:
        raise InjectedFault("after_inventory_decrement")

    return TestClient(app, raise_server_exceptions=False)


def test_business_error_envelope(client: TestClient) -> None:
    response = client.get("/api/business")
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "INSUFFICIENT_INVENTORY",
            "message": "short",
            "details": [{"product_id": 1}],
            "request_id": None,
        }
    }


def test_401_carries_www_authenticate(client: TestClient) -> None:
    response = client.get("/api/auth")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_validation_error_envelope(client: TestClient) -> None:
    response = client.post("/api/validate", json={"quantity": "lots"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["loc"] == ["body", "quantity"]
    assert error["details"][0]["type"] == "int_parsing"


def test_unexpected_error_does_not_leak_internals(client: TestClient) -> None:
    response = client.get("/api/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text


def test_injected_fault_is_distinguishable(client: TestClient) -> None:
    response = client.get("/api/fault")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INJECTED_FAULT"


def test_unknown_api_route_uses_envelope(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
