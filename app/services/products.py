from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import DuplicateSku, ProductNotFound
from app.models import Product
from app.schemas.product import ProductCreate, ProductUpdate


@dataclass(frozen=True)
class ProductFilters:
    search: str | None = None
    active: bool | None = None
    in_stock: bool | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None


def _filtered(query: Select[tuple[Product]], f: ProductFilters) -> Select[tuple[Product]]:
    if f.search:
        # Escape LIKE wildcards so a search for "100%" means the literal text.
        term = f.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{term}%"
        query = query.where(
            or_(
                Product.name.ilike(pattern, escape="\\"),
                Product.sku.ilike(pattern, escape="\\"),
                Product.description.ilike(pattern, escape="\\"),
            )
        )
    if f.active is not None:
        query = query.where(Product.is_active.is_(f.active))
    if f.in_stock is True:
        query = query.where(Product.inventory > 0)
    elif f.in_stock is False:
        query = query.where(Product.inventory == 0)
    if f.min_price is not None:
        query = query.where(Product.price >= f.min_price)
    if f.max_price is not None:
        query = query.where(Product.price <= f.max_price)
    return query


def list_products(
    db: Session, filters: ProductFilters, page: int, page_size: int
) -> tuple[list[Product], int]:
    base = _filtered(select(Product), filters)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(Product.id).offset((page - 1) * page_size).limit(page_size))
    return list(rows), total


def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise ProductNotFound(f"Product {product_id} not found", [{"product_id": product_id}])
    return product


def create_product(db: Session, data: ProductCreate) -> Product:
    product = Product(**data.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_products_sku" in str(exc.orig):
            raise DuplicateSku(f"SKU {data.sku} already exists", [{"sku": data.sku}]) from exc
        raise
    db.refresh(product)
    return product


def update_product(db: Session, product_id: int, data: ProductUpdate) -> Product:
    product = get_product(db, product_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


def set_inventory(db: Session, product_id: int, available: int) -> Product:
    product = db.scalar(select(Product).where(Product.id == product_id).with_for_update())
    if product is None:
        raise ProductNotFound(f"Product {product_id} not found", [{"product_id": product_id}])
    product.inventory = available
    db.commit()
    db.refresh(product)
    return product
