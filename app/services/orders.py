"""Order placement, retrieval and cancellation.

Atomicity:   validation, inventory decrement and order insert happen in ONE transaction;
             any exception rolls everything back.
Concurrency: product rows are locked with SELECT ... FOR UPDATE in ascending id order
             (a consistent lock order prevents deadlocks), so concurrent orders for the last
             unit are serialised and cannot oversell.
Idempotency: an optional Idempotency-Key is unique per user (database constraint).
             Same key + same payload replays the original order; same key + different
             payload is rejected with 409 IDEMPOTENCY_KEY_REUSED.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import IdempotencyKeyReused, OrderNotCancellable, OrderNotFound
from app.faults import fault_point
from app.models import Order, OrderItem, Product, User
from app.services import rules


@dataclass(frozen=True)
class PlacedOrder:
    order: Order
    replayed: bool


def request_fingerprint(lines: list[rules.OrderLine]) -> str:
    canonical = sorted((line.product_id, line.quantity) for line in lines)
    return hashlib.sha256(json.dumps(canonical).encode()).hexdigest()


def _find_by_idempotency_key(db: Session, user_id: int, key: str) -> Order | None:
    return db.scalar(select(Order).where(Order.user_id == user_id, Order.idempotency_key == key))


def _replay(existing: Order, fingerprint: str) -> PlacedOrder:
    if existing.request_hash != fingerprint:
        raise IdempotencyKeyReused(
            "Idempotency-Key was already used with a different request body",
            [{"order_id": str(existing.id)}],
        )
    return PlacedOrder(order=existing, replayed=True)


def lock_products(db: Session, product_ids: list[int]) -> dict[int, Product]:
    rows = db.scalars(
        select(Product).where(Product.id.in_(product_ids)).order_by(Product.id).with_for_update()
    )
    return {product.id: product for product in rows}


def build_order(user: User, priced: list[rules.PricedLine]) -> Order:
    return Order(
        id=uuid.uuid4(),
        user_id=user.id,
        customer_ref=user.customer_ref,
        status="confirmed",
        currency="USD",
        total=rules.order_total(line.line_total for line in priced),
        items=[
            OrderItem(
                product_id=line.product_id,
                sku=line.sku,
                product_name=line.product_name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
            for line in priced
        ],
    )


def create_order(
    db: Session, user: User, lines: list[rules.OrderLine], idempotency_key: str | None = None
) -> PlacedOrder:
    fingerprint = request_fingerprint(lines)
    if idempotency_key:
        existing = _find_by_idempotency_key(db, user.id, idempotency_key)
        if existing is not None:
            return _replay(existing, fingerprint)

    try:
        products = lock_products(db, [line.product_id for line in lines])
        rules.validate_order_lines(lines, products)
        priced = rules.price_lines(lines, products)

        for line in lines:
            products[line.product_id].inventory -= line.quantity
        fault_point("after_inventory_decrement")

        order = build_order(user, priced)
        order.idempotency_key = idempotency_key
        order.request_hash = fingerprint
        db.add(order)
        db.flush()
        fault_point("after_order_insert")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # A concurrent request with the same key committed first: replay its result.
        if idempotency_key and "uq_orders_user_idempotency_key" in str(exc.orig):
            existing = _find_by_idempotency_key(db, user.id, idempotency_key)
            if existing is not None:
                return _replay(existing, fingerprint)
        raise
    except Exception:
        db.rollback()
        raise
    return PlacedOrder(order=order, replayed=False)


def get_order(db: Session, user: User, order_id: uuid.UUID) -> Order:
    order = db.get(Order, order_id)
    # Other customers' orders are reported as missing so order ids cannot be probed.
    if order is None or (order.user_id != user.id and not user.is_admin):
        raise OrderNotFound(f"Order {order_id} not found", [{"order_id": str(order_id)}])
    return order


def list_orders(db: Session, user: User, page: int, page_size: int) -> tuple[list[Order], int]:
    total = db.scalar(select(func.count(Order.id)).where(Order.user_id == user.id)) or 0
    rows = db.scalars(
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc(), Order.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


def cancel_order(db: Session, user: User, order_id: uuid.UUID) -> Order:
    """Cancel a confirmed order and return its quantities to inventory, atomically."""
    try:
        order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order is None or (order.user_id != user.id and not user.is_admin):
            raise OrderNotFound(f"Order {order_id} not found", [{"order_id": str(order_id)}])
        if order.status != "confirmed":
            raise OrderNotCancellable(
                f"Order is already {order.status}", [{"status": order.status}]
            )
        products = lock_products(db, [item.product_id for item in order.items])
        for item in order.items:
            products[item.product_id].inventory += item.quantity
        order.status = "cancelled"
        db.commit()
    except Exception:
        db.rollback()
        raise
    return order
