"""Request schema validation: the first line of defence for the API contract."""

from decimal import Decimal
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from app.schemas.order import OrderCreate
from app.schemas.product import InventoryUpdate, ProductCreate


def error_types(exc: pytest.ExceptionInfo[ValidationError]) -> set[str]:
    return {e["type"] for e in exc.value.errors()}


class TestOrderCreate:
    def test_minimal_valid_order(self) -> None:
        order = OrderCreate.model_validate({"items": [{"product_id": 1, "quantity": 1}]})
        assert order.items[0].quantity == 1

    @pytest.mark.parametrize(
        ("quantity", "expected_type"),
        [
            (0, "greater_than_equal"),
            (-1, "greater_than_equal"),
            (1001, "less_than_equal"),
            (2**31, "less_than_equal"),
            ("2", "int_type"),  # strings are not coerced
            (2.0, "int_type"),  # nor are floats, even integral ones
            (1.5, "int_type"),
            (True, "int_type"),
            (None, "int_type"),
        ],
    )
    def test_quantity_boundaries_and_types(self, quantity: Any, expected_type: str) -> None:
        with pytest.raises(ValidationError) as exc:
            OrderCreate.model_validate({"items": [{"product_id": 1, "quantity": quantity}]})
        assert expected_type in error_types(exc)

    def test_quantity_upper_boundary_is_inclusive(self) -> None:
        OrderCreate.model_validate({"items": [{"product_id": 1, "quantity": 1000}]})

    @pytest.mark.parametrize(
        ("body", "expected_type"),
        [
            ({"items": []}, "too_short"),
            ({}, "missing"),
            ({"items": [{"product_id": 1}]}, "missing"),
            ({"items": [{"product_id": 0, "quantity": 1}]}, "greater_than_equal"),
            ({"items": [{"product_id": 1, "quantity": 1}], "total": "0.01"}, "extra_forbidden"),
            (
                {"items": [{"product_id": 1, "quantity": 1, "unit_price": "0.01"}]},
                "extra_forbidden",
            ),
            (
                {"items": [{"product_id": 1, "quantity": 1}, {"product_id": 1, "quantity": 2}]},
                "value_error",
            ),
            ({"items": [{"product_id": i, "quantity": 1} for i in range(1, 52)]}, "too_long"),
        ],
        ids=[
            "empty",
            "no-items",
            "missing-quantity",
            "product-id-zero",
            "client-total",
            "client-unit-price",
            "duplicate-product",
            "51-lines",
        ],
    )
    def test_invalid_bodies(self, body: dict[str, Any], expected_type: str) -> None:
        with pytest.raises(ValidationError) as exc:
            OrderCreate.model_validate(body)
        assert expected_type in error_types(exc)


class TestProductCreate:
    BASE: ClassVar[dict[str, Any]] = {"sku": "UNIT-001", "name": "Widget", "inventory": 1}

    @pytest.mark.parametrize("price", ["0.01", "999999.99", "19.9", 19.99, "1e2"])
    def test_valid_prices(self, price: Any) -> None:
        product = ProductCreate.model_validate({**self.BASE, "price": price})
        assert isinstance(product.price, Decimal)

    @pytest.mark.parametrize(
        ("price", "expected_type"),
        [
            ("0", "greater_than"),
            ("-1.00", "greater_than"),
            ("19.999", "decimal_max_places"),
            ("1000000.00", "decimal_whole_digits"),
            ("NaN", "finite_number"),
            ("abc", "decimal_parsing"),
            (True, "decimal_type"),
        ],
    )
    def test_invalid_prices(self, price: Any, expected_type: str) -> None:
        with pytest.raises(ValidationError) as exc:
            ProductCreate.model_validate({**self.BASE, "price": price})
        assert expected_type in error_types(exc)

    @pytest.mark.parametrize("sku", ["ab", "lower-case", "A", "X" * 33, "BAD SKU"])
    def test_invalid_sku(self, sku: str) -> None:
        with pytest.raises(ValidationError):
            ProductCreate.model_validate({**self.BASE, "sku": sku, "price": "1.00"})

    @pytest.mark.parametrize("inventory", [-1, 1_000_001, "5", 1.0])
    def test_invalid_inventory(self, inventory: Any) -> None:
        with pytest.raises(ValidationError):
            ProductCreate.model_validate({**self.BASE, "price": "1.00", "inventory": inventory})


@pytest.mark.parametrize("available", [0, 1_000_000])
def test_inventory_update_boundaries(available: int) -> None:
    assert InventoryUpdate(available=available).available == available


def test_inventory_update_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        InventoryUpdate(available=-1)
