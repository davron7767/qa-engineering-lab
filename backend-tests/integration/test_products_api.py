from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.seed import SEED_PRODUCTS
from app.models import Product


class TestListing:
    def test_lists_all_seed_products_in_id_order(self, client: TestClient) -> None:
        body = client.get("/api/v1/products").json()
        assert body["total"] == len(SEED_PRODUCTS)
        assert [p["sku"] for p in body["items"]] == [p.sku for p in SEED_PRODUCTS]

    def test_money_serialized_as_two_decimal_string(self, client: TestClient) -> None:
        item = client.get("/api/v1/products", params={"search": "QA-MN-003"}).json()["items"][0]
        assert item["price"] == "249.00"

    @pytest.mark.parametrize(
        ("params", "expected_skus"),
        [
            ({"search": "mouse"}, ["QA-MS-002"]),
            ({"search": "qa-hb"}, ["QA-HB-004"]),  # SKU, case-insensitive
            ({"search": "%"}, []),  # LIKE wildcards are escaped
            ({"active": "false"}, ["QA-LS-007"]),
            ({"in_stock": "false"}, ["QA-HB-004"]),
            ({"min_price": "59.50", "max_price": "89.99"}, ["QA-KB-001", "QA-WC-006"]),
        ],
    )
    def test_filters(self, client: TestClient, params: dict, expected_skus: list[str]) -> None:
        body = client.get("/api/v1/products", params=params).json()
        assert [p["sku"] for p in body["items"]] == expected_skus

    def test_pagination(self, client: TestClient) -> None:
        body = client.get("/api/v1/products", params={"page": 2, "page_size": 3}).json()
        assert (body["page"], body["page_size"], body["total"], body["pages"]) == (2, 3, 7, 3)
        assert [p["sku"] for p in body["items"]] == ["QA-HB-004", "QA-CT-005", "QA-WC-006"]

    @pytest.mark.parametrize(
        "params",
        [{"page": 0}, {"page_size": 101}, {"min_price": "10", "max_price": "5"}],
    )
    def test_invalid_query(self, client: TestClient, params: dict) -> None:
        response = client.get("/api/v1/products", params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestRetrieval:
    def test_get_product_and_inventory(self, client: TestClient) -> None:
        product = client.get("/api/v1/products/1").json()
        assert product["sku"] == "QA-KB-001"
        assert product["in_stock"] is True
        inventory = client.get("/api/v1/products/1/inventory").json()
        assert inventory["available"] == product["inventory"] == 25

    @pytest.mark.parametrize("product_id", [999, 2_147_483_647])
    def test_missing_product_is_404(self, client: TestClient, product_id: int) -> None:
        response = client.get(f"/api/v1/products/{product_id}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"

    @pytest.mark.parametrize("product_id", ["0", "-1", "abc", "2147483648"])
    def test_invalid_product_id_is_422(self, client: TestClient, product_id: str) -> None:
        assert client.get(f"/api/v1/products/{product_id}").status_code == 422


class TestAdministration:
    def test_create_product_persists(
        self, client: TestClient, admin_headers: dict, db: Session
    ) -> None:
        body = {"sku": "IT-NEW-1", "name": "New", "price": "12.30", "inventory": 4}
        response = client.post("/api/v1/products", json=body, headers=admin_headers)
        assert response.status_code == 201
        created = response.json()
        assert created["price"] == "12.30"
        assert created["is_active"] is True
        row = db.get(Product, created["id"])
        assert row is not None
        assert (row.price, row.inventory) == (Decimal("12.30"), 4)

    def test_duplicate_sku_conflicts(self, client: TestClient, admin_headers: dict) -> None:
        body = {"sku": "QA-KB-001", "name": "Dup", "price": "1.00", "inventory": 1}
        response = client.post("/api/v1/products", json=body, headers=admin_headers)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "SKU_ALREADY_EXISTS"

    @pytest.mark.parametrize(
        "overrides",
        [{"price": "0"}, {"price": "-5.00"}, {"price": "1.001"}, {"inventory": -1}],
        ids=["zero-price", "negative-price", "three-decimals", "negative-inventory"],
    )
    def test_invalid_product_rejected_and_not_persisted(
        self, client: TestClient, admin_headers: dict, db: Session, overrides: dict
    ) -> None:
        body = {"sku": "IT-BAD-1", "name": "Bad", "price": "1.00", "inventory": 1, **overrides}
        response = client.post("/api/v1/products", json=body, headers=admin_headers)
        assert response.status_code == 422
        assert db.scalar(select(Product).where(Product.sku == "IT-BAD-1")) is None

    def test_update_price_and_deactivate(self, client: TestClient, admin_headers: dict) -> None:
        response = client.patch(
            "/api/v1/products/2", json={"price": "24.50", "is_active": False}, headers=admin_headers
        )
        assert response.status_code == 200
        assert (response.json()["price"], response.json()["is_active"]) == ("24.50", False)

    def test_set_inventory(self, client: TestClient, admin_headers: dict) -> None:
        response = client.put(
            "/api/v1/products/4/inventory", json={"available": 7}, headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["available"] == 7
        assert client.get("/api/v1/products/4").json()["in_stock"] is True


class TestDatabaseConstraints:
    """Defence in depth: even a buggy service cannot persist invalid values."""

    @pytest.mark.parametrize(
        ("statement", "constraint"),
        [
            (
                "UPDATE products SET inventory = -1 WHERE id = 1",
                "ck_products_inventory_non_negative",
            ),
            ("UPDATE products SET price = 0 WHERE id = 1", "ck_products_price_positive"),
            ("UPDATE products SET sku = 'QA-MS-002' WHERE id = 1", "uq_products_sku"),
        ],
    )
    def test_constraint_violations(self, db: Session, statement: str, constraint: str) -> None:
        with pytest.raises(IntegrityError, match=constraint):
            db.execute(text(statement))
        db.rollback()
