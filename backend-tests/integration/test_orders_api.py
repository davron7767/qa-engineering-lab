import threading
import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from support import CUSTOMER

from app.db.session import get_session_factory
from app.errors import AppError, InsufficientInventory
from app.models import Order, OrderItem, Product, User
from app.services import orders as order_service
from app.services.rules import OrderLine

ORDERS = "/api/v1/orders"


def order_count(db: Session) -> int:
    db.expire_all()
    return db.scalar(select(func.count(Order.id))) or 0


def inventory(db: Session, product_id: int) -> int:
    db.expire_all()
    return db.get(Product, product_id).inventory  # type: ignore[union-attr]


def place(client: TestClient, headers: dict, items: list[dict], **extra_headers: str):
    return client.post(ORDERS, json={"items": items}, headers={**headers, **extra_headers})


class TestPlaceOrder:
    def test_success_persists_order_lines_and_decrements_inventory(
        self, client: TestClient, customer_headers: dict, db: Session
    ) -> None:
        response = place(
            client,
            customer_headers,
            [{"product_id": 5, "quantity": 3}, {"product_id": 2, "quantity": 2}],
        )
        assert response.status_code == 201
        body = response.json()
        assert response.headers["Location"] == f"{ORDERS}/{body['id']}"
        assert body["status"] == "confirmed"
        assert body["customer_ref"] == "CUST-000002"
        assert body["total"] == "60.85"  # 3 x 0.29 + 2 x 29.99
        assert [
            (i["sku"], i["quantity"], i["unit_price"], i["line_total"]) for i in body["items"]
        ] == [
            ("QA-CT-005", 3, "0.29", "0.87"),
            ("QA-MS-002", 2, "29.99", "59.98"),
        ]

        order = db.get(Order, uuid.UUID(body["id"]))
        assert order is not None
        assert order.total == Decimal("60.85")
        assert len(order.items) == 2
        assert inventory(db, 5) == 997
        assert inventory(db, 2) == 48

    def test_order_exactly_all_remaining_stock(
        self, client: TestClient, customer_headers: dict, db: Session
    ) -> None:
        assert (
            place(client, customer_headers, [{"product_id": 3, "quantity": 3}]).status_code == 201
        )
        assert inventory(db, 3) == 0

    def test_unit_price_snapshot_survives_price_change(
        self, client: TestClient, customer_headers: dict, admin_headers: dict
    ) -> None:
        order_id = place(client, customer_headers, [{"product_id": 1, "quantity": 1}]).json()["id"]
        client.patch("/api/v1/products/1", json={"price": "1.00"}, headers=admin_headers)
        order = client.get(f"{ORDERS}/{order_id}", headers=customer_headers).json()
        assert order["items"][0]["unit_price"] == "89.99"
        assert order["total"] == "89.99"


class TestRejectedOrdersLeaveNoTrace:
    @pytest.mark.parametrize(
        ("items", "status", "code"),
        [
            ([{"product_id": 3, "quantity": 4}], 409, "INSUFFICIENT_INVENTORY"),
            ([{"product_id": 4, "quantity": 1}], 409, "INSUFFICIENT_INVENTORY"),  # stock 0
            ([{"product_id": 7, "quantity": 1}], 400, "PRODUCT_INACTIVE"),
            ([{"product_id": 999, "quantity": 1}], 400, "UNKNOWN_PRODUCT"),
            # The first line is valid; the second fails. Nothing may be applied.
            (
                [{"product_id": 1, "quantity": 2}, {"product_id": 3, "quantity": 99}],
                409,
                "INSUFFICIENT_INVENTORY",
            ),
            ([{"product_id": 1, "quantity": 0}], 422, "VALIDATION_ERROR"),
        ],
        ids=["over-stock", "out-of-stock", "inactive", "unknown", "partial-multi-line", "zero"],
    )
    def test_rejection_has_no_side_effects(
        self, client: TestClient, customer_headers: dict, db: Session, items, status, code
    ) -> None:
        before = {pid: inventory(db, pid) for pid in (1, 3, 4, 7)}
        response = place(client, customer_headers, items)
        assert response.status_code == status, response.text
        assert response.json()["error"]["code"] == code
        assert order_count(db) == 0
        assert db.scalar(select(func.count(OrderItem.id))) == 0
        assert {pid: inventory(db, pid) for pid in before} == before

    def test_insufficient_inventory_details(
        self, client: TestClient, customer_headers: dict
    ) -> None:
        response = place(client, customer_headers, [{"product_id": 3, "quantity": 4}])
        assert response.json()["error"]["details"] == [
            {"product_id": 3, "sku": "QA-MN-003", "requested": 4, "available": 3}
        ]

    @pytest.mark.parametrize("fault", ["after_inventory_decrement", "after_order_insert"])
    def test_failure_mid_transaction_rolls_back_everything(
        self, lenient_client: TestClient, customer_headers: dict, db: Session, fault: str
    ) -> None:
        response = place(
            lenient_client,
            customer_headers,
            [{"product_id": 1, "quantity": 5}],
            **{"X-Test-Fault": fault},
        )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INJECTED_FAULT"
        assert inventory(db, 1) == 25
        assert order_count(db) == 0

    def test_client_cannot_supply_total(self, client: TestClient, customer_headers: dict) -> None:
        response = client.post(
            ORDERS,
            json={"items": [{"product_id": 1, "quantity": 1}], "total": "0.01"},
            headers=customer_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["loc"] == ["body", "total"]


class TestIdempotency:
    def test_same_key_same_body_replays(
        self, client: TestClient, customer_headers: dict, db: Session
    ) -> None:
        items = [{"product_id": 2, "quantity": 1}]
        first = place(client, customer_headers, items, **{"Idempotency-Key": "it-key-1"})
        second = place(client, customer_headers, items, **{"Idempotency-Key": "it-key-1"})
        assert (first.status_code, second.status_code) == (201, 200)
        assert second.headers["Idempotent-Replayed"] == "true"
        assert second.json() == first.json()
        assert order_count(db) == 1
        assert inventory(db, 2) == 49

    def test_same_key_different_body_conflicts(
        self, client: TestClient, customer_headers: dict, db: Session
    ) -> None:
        place(
            client,
            customer_headers,
            [{"product_id": 2, "quantity": 1}],
            **{"Idempotency-Key": "k2"},
        )
        response = place(
            client,
            customer_headers,
            [{"product_id": 2, "quantity": 2}],
            **{"Idempotency-Key": "k2"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        assert order_count(db) == 1

    def test_keys_are_scoped_per_user(
        self, client: TestClient, customer_headers: dict, customer2_headers: dict, db: Session
    ) -> None:
        items = [{"product_id": 2, "quantity": 1}]
        a = place(client, customer_headers, items, **{"Idempotency-Key": "shared"})
        b = place(client, customer2_headers, items, **{"Idempotency-Key": "shared"})
        assert (a.status_code, b.status_code) == (201, 201)
        assert a.json()["id"] != b.json()["id"]

    @pytest.mark.parametrize("key", ["", "has space", "x" * 65, "semi;colon"])
    def test_invalid_key_rejected(
        self, client: TestClient, customer_headers: dict, key: str
    ) -> None:
        response = place(
            client, customer_headers, [{"product_id": 2, "quantity": 1}], **{"Idempotency-Key": key}
        )
        assert response.status_code == 422


def run_concurrently(count: int, action: Callable[[], object]) -> list[object]:
    """Release `count` threads at the same instant and collect each result or exception."""
    barrier = threading.Barrier(count)
    results: list[object] = [None] * count

    def worker(index: int) -> None:
        barrier.wait()
        try:
            results[index] = action()
        except Exception as exc:
            results[index] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def place_via_service(user_email: str, product_id: int, quantity: int, key: str | None = None):
    with get_session_factory()() as session:
        user = session.scalar(select(User).where(User.email == user_email))
        assert user is not None
        return order_service.create_order(session, user, [OrderLine(product_id, quantity)], key)


class TestConcurrency:
    def test_last_unit_sold_exactly_once(self, make_product, db: Session) -> None:
        product = make_product(inventory=1)
        results = run_concurrently(10, lambda: place_via_service(CUSTOMER[0], product["id"], 1))
        successes = [r for r in results if isinstance(r, order_service.PlacedOrder)]
        rejections = [r for r in results if isinstance(r, InsufficientInventory)]
        assert len(successes) == 1, results
        assert len(rejections) == 9, results
        assert inventory(db, product["id"]) == 0

    def test_concurrent_partial_stock_never_oversells(self, make_product, db: Session) -> None:
        product = make_product(inventory=10)
        results = run_concurrently(8, lambda: place_via_service(CUSTOMER[0], product["id"], 3))
        sold = sum(3 for r in results if isinstance(r, order_service.PlacedOrder))
        assert all(isinstance(r, order_service.PlacedOrder | AppError) for r in results), results
        assert sold == 9  # three orders of 3 fit into 10; the fourth would oversell
        assert inventory(db, product["id"]) == 1

    def test_concurrent_duplicate_submissions_create_one_order(
        self, make_product, db: Session
    ) -> None:
        product = make_product(inventory=50)
        results = run_concurrently(
            6, lambda: place_via_service(CUSTOMER[0], product["id"], 2, key="double-click")
        )
        assert all(isinstance(r, order_service.PlacedOrder) for r in results), results
        ids = {r.order.id for r in results}  # type: ignore[union-attr]
        assert len(ids) == 1
        assert sum(1 for r in results if not r.replayed) == 1  # type: ignore[union-attr]
        assert inventory(db, product["id"]) == 48


class TestRetrievalAndHistory:
    def test_other_customers_order_is_hidden(
        self,
        client: TestClient,
        customer_headers: dict,
        customer2_headers: dict,
        admin_headers: dict,
    ) -> None:
        order_id = place(client, customer_headers, [{"product_id": 1, "quantity": 1}]).json()["id"]
        response = client.get(f"{ORDERS}/{order_id}", headers=customer2_headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"
        assert client.get(f"{ORDERS}/{order_id}", headers=admin_headers).status_code == 200

    def test_unknown_and_malformed_order_ids(
        self, client: TestClient, customer_headers: dict
    ) -> None:
        assert client.get(f"{ORDERS}/{uuid.uuid4()}", headers=customer_headers).status_code == 404
        assert client.get(f"{ORDERS}/not-a-uuid", headers=customer_headers).status_code == 422

    def test_history_is_own_orders_newest_first_and_paginated(
        self, client: TestClient, customer_headers: dict, customer2_headers: dict
    ) -> None:
        ids = [
            place(client, customer_headers, [{"product_id": 2, "quantity": 1}]).json()["id"]
            for _ in range(3)
        ]
        place(client, customer2_headers, [{"product_id": 2, "quantity": 1}])
        page1 = client.get(ORDERS, params={"page_size": 2}, headers=customer_headers).json()
        page2 = client.get(
            ORDERS, params={"page": 2, "page_size": 2}, headers=customer_headers
        ).json()
        assert (page1["total"], page1["pages"]) == (3, 2)
        assert [o["id"] for o in page1["items"] + page2["items"]] == list(reversed(ids))


class TestCancellation:
    def test_cancel_restores_inventory(
        self, client: TestClient, customer_headers: dict, db: Session
    ) -> None:
        order_id = place(client, customer_headers, [{"product_id": 6, "quantity": 4}]).json()["id"]
        assert inventory(db, 6) == 6
        response = client.post(f"{ORDERS}/{order_id}/cancel", headers=customer_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert inventory(db, 6) == 10

    def test_cancel_twice_conflicts(
        self, client: TestClient, customer_headers: dict, db: Session
    ) -> None:
        order_id = place(client, customer_headers, [{"product_id": 6, "quantity": 1}]).json()["id"]
        client.post(f"{ORDERS}/{order_id}/cancel", headers=customer_headers)
        response = client.post(f"{ORDERS}/{order_id}/cancel", headers=customer_headers)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ORDER_NOT_CANCELLABLE"
        assert inventory(db, 6) == 10  # restored once, not twice

    def test_cannot_cancel_someone_elses_order(
        self, client: TestClient, customer_headers: dict, customer2_headers: dict
    ) -> None:
        order_id = place(client, customer_headers, [{"product_id": 6, "quantity": 1}]).json()["id"]
        assert (
            client.post(f"{ORDERS}/{order_id}/cancel", headers=customer2_headers).status_code == 404
        )
