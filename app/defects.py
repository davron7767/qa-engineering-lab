"""DEFECT LABORATORY - deliberately broken implementations. Never active by default.

Activated only by DEFECT_MODE=<name> (refused when APP_ENV=production). Each defect replaces
one function of the correct implementation at startup, so the normal code paths stay clean and
the bug is isolated in this file. See docs/defect-lab.md for impact, detection and reproduction.

    wrong_total                  money computed with binary floats and truncated to cents
    inventory_before_validation  stock reserved and committed before the whole order is validated
    persist_rejected_order       order header committed before validation; rejections leave orphans
    oversell_race                read-modify-write without row locks (lost update under concurrency)
"""

import logging
import time
import uuid
from collections.abc import Callable
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.faults import fault_point
from app.models import Order, Product, User
from app.services import orders, rules
from app.services.orders import PlacedOrder

logger = logging.getLogger("qa_commerce.defects")


# --- 1. wrong_total ---------------------------------------------------------------------------
def float_line_total(unit_price: Decimal, quantity: int) -> Decimal:
    # BUG: float arithmetic + truncation. 0.29 * 3 = 0.8699999999999999 -> 0.86
    cents = int(float(unit_price) * quantity * 100)
    return Decimal(cents) / 100


# --- 2. inventory_before_validation -----------------------------------------------------------
def create_order_reserving_early(
    db: Session, user: User, lines: list[rules.OrderLine], idempotency_key: str | None = None
) -> PlacedOrder:
    fingerprint = orders.request_fingerprint(lines)
    products = orders.lock_products(db, [line.product_id for line in lines])
    snapshot = {
        pid: SimpleNamespace(
            **{k: getattr(p, k) for k in ("id", "sku", "name", "price", "inventory", "is_active")}
        )
        for pid, p in products.items()
    }
    for line in lines:
        product = products.get(line.product_id)
        if product is not None and product.is_active and product.inventory >= line.quantity:
            product.inventory -= line.quantity
    db.commit()  # BUG: the "reservation" is committed before the whole order is known to be valid
    fault_point("after_inventory_decrement")

    rules.validate_order_lines(lines, snapshot)  # a failure here leaves the stock reserved
    order = orders.build_order(user, rules.price_lines(lines, snapshot))
    order.idempotency_key, order.request_hash = idempotency_key, fingerprint
    db.add(order)
    db.flush()
    fault_point("after_order_insert")
    db.commit()
    return PlacedOrder(order=order, replayed=False)


# --- 3. persist_rejected_order ----------------------------------------------------------------
def create_order_header_first(
    db: Session, user: User, lines: list[rules.OrderLine], idempotency_key: str | None = None
) -> PlacedOrder:
    fingerprint = orders.request_fingerprint(lines)
    # BUG: the order row is committed first "to get an id", before any validation.
    order = Order(
        id=uuid.uuid4(),
        user_id=user.id,
        customer_ref=user.customer_ref,
        status="confirmed",
        currency="USD",
        total=Decimal("0.00"),
        idempotency_key=idempotency_key,
        request_hash=fingerprint,
    )
    db.add(order)
    db.commit()

    products = orders.lock_products(db, [line.product_id for line in lines])
    rules.validate_order_lines(lines, products)  # raises -> empty "confirmed" order remains
    priced = rules.price_lines(lines, products)
    for line in lines:
        products[line.product_id].inventory -= line.quantity
    fault_point("after_inventory_decrement")
    complete = orders.build_order(user, priced)
    order.items, order.total = complete.items, complete.total
    db.flush()
    fault_point("after_order_insert")
    db.commit()
    return PlacedOrder(order=order, replayed=False)


# --- 4. oversell_race ---------------------------------------------------------------------------
def create_order_without_locks(
    db: Session, user: User, lines: list[rules.OrderLine], idempotency_key: str | None = None
) -> PlacedOrder:
    fingerprint = orders.request_fingerprint(lines)
    # BUG: plain SELECT - no FOR UPDATE - so concurrent requests all see the same stock level.
    rows = db.scalars(select(Product).where(Product.id.in_([ln.product_id for ln in lines])))
    products = {p.id: p for p in rows}
    rules.validate_order_lines(lines, products)
    priced = rules.price_lines(lines, products)
    time.sleep(0.05)  # stands in for real work between check and write (e.g. a payment call)
    for line in lines:
        product = products[line.product_id]
        product.inventory = product.inventory - line.quantity  # lost update: absolute write
    fault_point("after_inventory_decrement")
    order = orders.build_order(user, priced)
    order.idempotency_key, order.request_hash = idempotency_key, fingerprint
    db.add(order)
    db.flush()
    fault_point("after_order_insert")
    db.commit()
    return PlacedOrder(order=order, replayed=False)


_PATCHES: dict[str, Callable[[], None]] = {
    "wrong_total": lambda: setattr(rules, "line_total", float_line_total),
    "inventory_before_validation": lambda: setattr(
        orders, "create_order", create_order_reserving_early
    ),
    "persist_rejected_order": lambda: setattr(orders, "create_order", create_order_header_first),
    "oversell_race": lambda: setattr(orders, "create_order", create_order_without_locks),
}


def activate(mode: str) -> None:
    if mode not in _PATCHES:
        raise ValueError(f"Unknown DEFECT_MODE '{mode}'. Choose one of: {', '.join(_PATCHES)}")
    _PATCHES[mode]()
    logger.warning("DEFECT LAB: '%s' is active. This instance is intentionally broken.", mode)
