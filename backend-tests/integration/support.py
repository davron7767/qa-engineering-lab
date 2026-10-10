"""Shared constants and helpers for integration tests (importable as `support`)."""

from fastapi.testclient import TestClient

# Local-only seed credentials (see .env.example); integration tests set these explicitly.
ADMIN = ("admin@qa-commerce.test", "Admin#Local2024")
CUSTOMER = ("customer@qa-commerce.test", "Customer#Local2024")
CUSTOMER2 = ("customer2@qa-commerce.test", "Customer#Local2024")


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
