from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from support import ADMIN, CUSTOMER, login

from app.models import AuthSession, User
from app.security import hash_token


def test_login_returns_token_and_user(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": CUSTOMER[0], "password": CUSTOMER[1]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) >= 40
    assert body["user"] == {
        "id": body["user"]["id"],
        "email": CUSTOMER[0],
        "full_name": "Casey Customer",
        "role": "customer",
        "customer_ref": "CUST-000002",
    }


def test_only_token_hash_is_persisted(client: TestClient, db: Session) -> None:
    token = login(client, *CUSTOMER)["Authorization"].removeprefix("Bearer ")
    stored = db.scalars(select(AuthSession.token_hash)).all()
    assert hash_token(token) in stored
    assert token not in stored


def test_email_is_case_insensitive(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": CUSTOMER[0].upper(), "password": CUSTOMER[1]}
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "credentials",
    [
        {"email": CUSTOMER[0], "password": "wrong-password"},
        {"email": "nobody@qa-commerce.test", "password": CUSTOMER[1]},
    ],
    ids=["wrong-password", "unknown-email"],
)
def test_bad_credentials_are_indistinguishable(client: TestClient, credentials: dict) -> None:
    response = client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert response.json()["error"]["message"] == "Invalid email or password"


def test_password_hash_never_returned(client: TestClient, customer_headers: dict) -> None:
    body = client.get("/api/v1/auth/me", headers=customer_headers).text
    assert "argon2" not in body
    assert "password" not in body


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer"}, {"Authorization": "Basic Zm9vOmJhcg=="}],
    ids=["missing", "empty-bearer", "basic-scheme"],
)
def test_missing_credentials_rejected(client: TestClient, headers: dict) -> None:
    response = client.get("/api/v1/orders", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_unknown_token_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/orders", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_logout_revokes_token(client: TestClient, customer_headers: dict) -> None:
    assert client.post("/api/v1/auth/logout", headers=customer_headers).status_code == 204
    response = client.get("/api/v1/auth/me", headers=customer_headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_expired_session_rejected(client: TestClient, customer_headers: dict, db: Session) -> None:
    db.execute(update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    response = client.get("/api/v1/auth/me", headers=customer_headers)
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"]


class TestAdminOnly:
    def test_customer_cannot_create_product(
        self, client: TestClient, customer_headers: dict
    ) -> None:
        body = {"sku": "NOPE-1", "name": "x", "price": "1.00", "inventory": 1}
        response = client.post("/api/v1/products", json=body, headers=customer_headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    def test_customer_cannot_set_inventory(
        self, client: TestClient, customer_headers: dict
    ) -> None:
        response = client.put(
            "/api/v1/products/1/inventory", json={"available": 999}, headers=customer_headers
        )
        assert response.status_code == 403

    def test_admin_creates_user(self, client: TestClient, admin_headers: dict, db: Session) -> None:
        body = {"email": "New.User@QA-Commerce.test", "full_name": "New", "password": "x" * 12}
        response = client.post("/api/v1/users", json=body, headers=admin_headers)
        assert response.status_code == 201
        assert response.json()["email"] == "new.user@qa-commerce.test"
        assert response.json()["customer_ref"].startswith("CUST-")
        assert db.scalar(select(User).where(User.email == "new.user@qa-commerce.test"))
        assert client.post("/api/v1/users", json=body, headers=admin_headers).status_code == 409

    def test_short_password_rejected(self, client: TestClient, admin_headers: dict) -> None:
        body = {"email": "short@qa-commerce.test", "full_name": "S", "password": "x" * 11}
        response = client.post("/api/v1/users", json=body, headers=admin_headers)
        assert response.status_code == 422


def test_admin_login_has_admin_role(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
    assert response.json()["user"]["role"] == "admin"
