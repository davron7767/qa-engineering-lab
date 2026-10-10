import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import Money, PageMeta, StrictModel
from app.services.rules import MAX_LINES_PER_ORDER, MAX_QUANTITY_PER_LINE

INT32_MAX = 2_147_483_647


class OrderItemIn(StrictModel):
    # strict=True: "2", 2.0 and true are rejected - quantities must be JSON integers.
    product_id: int = Field(ge=1, le=INT32_MAX, strict=True)
    quantity: int = Field(ge=1, le=MAX_QUANTITY_PER_LINE, strict=True)


class OrderCreate(StrictModel):
    items: list[OrderItemIn] = Field(min_length=1, max_length=MAX_LINES_PER_ORDER)

    @field_validator("items")
    @classmethod
    def _unique_products(cls, items: list[OrderItemIn]) -> list[OrderItemIn]:
        ids = [item.product_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("each product may appear only once per order")
        return items

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"items": [{"product_id": 1, "quantity": 2}]}]}
    )


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    sku: str
    product_name: str
    quantity: int
    unit_price: Money
    line_total: Money


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_ref: str
    status: Literal["confirmed", "cancelled"]
    currency: Literal["USD"]
    items: list[OrderItemOut]
    total: Money
    created_at: datetime


class OrderPage(PageMeta):
    items: list[OrderOut]
