from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.schemas.common import Money, PageMeta, PriceIn, StrictModel

MAX_INVENTORY = 1_000_000


class ProductCreate(StrictModel):
    sku: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,31}$", examples=["QA-KB-001"])
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    price: PriceIn
    inventory: int = Field(ge=0, le=MAX_INVENTORY, strict=True)
    is_active: bool = True


class ProductUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    price: PriceIn | None = None
    is_active: bool | None = None


class InventoryUpdate(StrictModel):
    available: int = Field(ge=0, le=MAX_INVENTORY, strict=True)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: str
    price: Money
    inventory: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def in_stock(self) -> bool:
        return self.inventory > 0


class ProductPage(PageMeta):
    items: list[ProductOut]


class InventoryOut(BaseModel):
    product_id: int
    sku: str
    available: int
    in_stock: bool
    updated_at: datetime
