"""Pure order business rules: validation and pricing. No database access, fully unit-testable.

Money is always `Decimal`; floats are rejected outright so binary rounding can never leak in.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from app.errors import InsufficientInventory, ProductInactive, UnknownProduct

CENT = Decimal("0.01")
MAX_QUANTITY_PER_LINE = 1000
MAX_LINES_PER_ORDER = 50


class ProductLike(Protocol):
    id: int
    sku: str
    name: str
    price: Decimal
    inventory: int
    is_active: bool


@dataclass(frozen=True)
class OrderLine:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class PricedLine:
    product_id: int
    sku: str
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


def to_money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"money must be Decimal, got {type(value).__name__}")
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(unit_price: Decimal, quantity: int) -> Decimal:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ValueError(f"quantity must be a positive integer, got {quantity!r}")
    return to_money(to_money(unit_price) * quantity)


def order_total(line_totals: Iterable[Decimal]) -> Decimal:
    return to_money(sum(line_totals, Decimal("0")))


def validate_order_lines(lines: Sequence[OrderLine], products: Mapping[int, ProductLike]) -> None:
    """Raise the first applicable business-rule error, checked in this documented order:
    unknown product -> inactive product -> insufficient inventory (all short lines reported)."""
    unknown = [line.product_id for line in lines if line.product_id not in products]
    if unknown:
        raise UnknownProduct(
            "One or more products do not exist",
            [{"product_id": pid} for pid in unknown],
        )

    inactive = [
        products[line.product_id] for line in lines if not products[line.product_id].is_active
    ]
    if inactive:
        raise ProductInactive(
            "One or more products are not available for ordering",
            [{"product_id": p.id, "sku": p.sku} for p in inactive],
        )

    short = [
        {
            "product_id": line.product_id,
            "sku": products[line.product_id].sku,
            "requested": line.quantity,
            "available": products[line.product_id].inventory,
        }
        for line in lines
        if line.quantity > products[line.product_id].inventory
    ]
    if short:
        raise InsufficientInventory("Insufficient inventory for one or more items", short)


def price_lines(
    lines: Sequence[OrderLine], products: Mapping[int, ProductLike]
) -> list[PricedLine]:
    """Price lines from the server-side catalogue; client-supplied prices are never used."""
    priced = []
    for line in lines:
        product = products[line.product_id]
        priced.append(
            PricedLine(
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                quantity=line.quantity,
                unit_price=to_money(product.price),
                line_total=line_total(product.price, line.quantity),
            )
        )
    return priced
