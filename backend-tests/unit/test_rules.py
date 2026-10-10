"""Pure business rules: pricing, quantity validation and order-line validation."""

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.errors import InsufficientInventory, ProductInactive, UnknownProduct
from app.services import rules
from app.services.rules import OrderLine


@dataclass
class FakeProduct:
    id: int
    sku: str
    name: str
    price: Decimal
    inventory: int
    is_active: bool = True


def catalogue(*products: FakeProduct) -> dict[int, FakeProduct]:
    return {p.id: p for p in products}


KEYBOARD = FakeProduct(1, "KB", "Keyboard", Decimal("89.99"), 5)
TIES = FakeProduct(2, "TIES", "Cable ties", Decimal("0.29"), 1000)
RETIRED = FakeProduct(3, "OLD", "Retired", Decimal("10.00"), 5, is_active=False)


class TestLineTotal:
    @pytest.mark.parametrize(
        ("price", "quantity", "expected"),
        [
            ("0.10", 3, "0.30"),  # 0.1 * 3 == 0.30000000000000004 in binary floating point
            ("0.29", 3, "0.87"),  # float(0.29) * 3 == 0.8699999999999999
            ("19.99", 3, "59.97"),
            ("0.01", 1, "0.01"),  # smallest price
            ("999999.99", 1000, "999999990.00"),  # largest price x largest quantity
        ],
    )
    def test_is_exact_decimal_arithmetic(self, price: str, quantity: int, expected: str) -> None:
        result = rules.line_total(Decimal(price), quantity)
        assert result == Decimal(expected)
        assert result.as_tuple().exponent == -2, "money must carry exactly two decimal places"

    @pytest.mark.parametrize("quantity", [0, -1, True, 1.5, "2"])
    def test_rejects_non_positive_or_non_integer_quantity(self, quantity: object) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            rules.line_total(Decimal("1.00"), quantity)  # type: ignore[arg-type]

    def test_rejects_float_price(self) -> None:
        with pytest.raises(TypeError, match="Decimal"):
            rules.line_total(0.29, 3)  # type: ignore[arg-type]


class TestOrderTotal:
    def test_sums_line_totals(self) -> None:
        assert rules.order_total([Decimal("0.87"), Decimal("29.99")]) == Decimal("30.86")

    def test_empty_is_zero_with_two_places(self) -> None:
        assert str(rules.order_total([])) == "0.00"

    def test_rounds_half_up_to_cents(self) -> None:
        assert rules.to_money(Decimal("0.005")) == Decimal("0.01")
        assert rules.to_money(Decimal("0.0049")) == Decimal("0.00")


class TestValidateOrderLines:
    def test_valid_lines_pass(self) -> None:
        rules.validate_order_lines([OrderLine(1, 5), OrderLine(2, 1)], catalogue(KEYBOARD, TIES))

    def test_quantity_equal_to_inventory_is_allowed(self) -> None:
        rules.validate_order_lines([OrderLine(1, KEYBOARD.inventory)], catalogue(KEYBOARD))

    def test_unknown_product_reported_with_ids(self) -> None:
        with pytest.raises(UnknownProduct) as exc:
            rules.validate_order_lines([OrderLine(1, 1), OrderLine(99, 1)], catalogue(KEYBOARD))
        assert exc.value.details == [{"product_id": 99}]
        assert exc.value.status_code == 400

    def test_inactive_product_rejected(self) -> None:
        with pytest.raises(ProductInactive) as exc:
            rules.validate_order_lines([OrderLine(3, 1)], catalogue(RETIRED))
        assert exc.value.details == [{"product_id": 3, "sku": "OLD"}]

    def test_insufficient_inventory_lists_every_short_line(self) -> None:
        lines = [OrderLine(1, 6), OrderLine(2, 1001)]
        with pytest.raises(InsufficientInventory) as exc:
            rules.validate_order_lines(lines, catalogue(KEYBOARD, TIES))
        assert exc.value.status_code == 409
        assert exc.value.details == [
            {"product_id": 1, "sku": "KB", "requested": 6, "available": 5},
            {"product_id": 2, "sku": "TIES", "requested": 1001, "available": 1000},
        ]

    def test_rule_precedence_unknown_before_inactive_before_inventory(self) -> None:
        products = catalogue(KEYBOARD, RETIRED)
        with pytest.raises(UnknownProduct):
            rules.validate_order_lines(
                [OrderLine(1, 99), OrderLine(3, 1), OrderLine(42, 1)], products
            )
        with pytest.raises(ProductInactive):
            rules.validate_order_lines([OrderLine(1, 99), OrderLine(3, 1)], products)


class TestPriceLines:
    def test_uses_catalogue_price_and_snapshots_product(self) -> None:
        [line] = rules.price_lines([OrderLine(2, 3)], catalogue(TIES))
        assert line == rules.PricedLine(
            product_id=2,
            sku="TIES",
            product_name="Cable ties",
            quantity=3,
            unit_price=Decimal("0.29"),
            line_total=Decimal("0.87"),
        )
