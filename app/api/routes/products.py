from decimal import Decimal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.errors import AppError
from app.models import Product, User
from app.schemas.common import error_responses, page_count
from app.schemas.order import INT32_MAX
from app.schemas.product import (
    InventoryOut,
    InventoryUpdate,
    ProductCreate,
    ProductOut,
    ProductPage,
    ProductUpdate,
)
from app.services import products as product_service

router = APIRouter(prefix="/products", tags=["products"])

ProductId = Path(ge=1, le=INT32_MAX, description="Product id")


class InvalidPriceRange(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


def _inventory(product: Product) -> InventoryOut:
    return InventoryOut(
        product_id=product.id,
        sku=product.sku,
        available=product.inventory,
        in_stock=product.inventory > 0,
        updated_at=product.updated_at,
    )


@router.get(
    "",
    response_model=ProductPage,
    summary="List and filter products",
    responses=error_responses(422),
)
def list_products(
    search: str | None = Query(None, max_length=100, description="Matches name, SKU, description"),
    active: bool | None = Query(None, description="Filter by active status"),
    in_stock: bool | None = Query(None, description="true: inventory > 0, false: inventory = 0"),
    min_price: Decimal | None = Query(None, ge=0),
    max_price: Decimal | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ProductPage:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise InvalidPriceRange(
            "min_price must not exceed max_price",
            [{"loc": ["query", "min_price"], "msg": "greater than max_price"}],
        )
    filters = product_service.ProductFilters(search, active, in_stock, min_price, max_price)
    rows, total = product_service.list_products(db, filters, page, page_size)
    return ProductPage(
        items=[ProductOut.model_validate(p) for p in rows],
        page=page,
        page_size=page_size,
        total=total,
        pages=page_count(total, page_size),
    )


@router.get(
    "/{product_id}",
    response_model=ProductOut,
    summary="Get a product",
    responses=error_responses(404, 422),
)
def get_product(product_id: int = ProductId, db: Session = Depends(get_db)) -> Product:
    return product_service.get_product(db, product_id)


@router.get(
    "/{product_id}/inventory",
    response_model=InventoryOut,
    summary="Get available inventory for a product",
    responses=error_responses(404, 422),
)
def get_inventory(product_id: int = ProductId, db: Session = Depends(get_db)) -> InventoryOut:
    return _inventory(product_service.get_product(db, product_id))


@router.post(
    "",
    response_model=ProductOut,
    status_code=201,
    summary="Create a product (admin only)",
    responses=error_responses(401, 403, 409, 422),
)
def create_product(
    body: ProductCreate, _admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> Product:
    return product_service.create_product(db, body)


@router.patch(
    "/{product_id}",
    response_model=ProductOut,
    summary="Update product details, price or active status (admin only)",
    responses=error_responses(401, 403, 404, 422),
)
def update_product(
    body: ProductUpdate,
    product_id: int = ProductId,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Product:
    return product_service.update_product(db, product_id, body)


@router.put(
    "/{product_id}/inventory",
    response_model=InventoryOut,
    summary="Set available inventory (admin only)",
    responses=error_responses(401, 403, 404, 422),
)
def set_inventory(
    body: InventoryUpdate,
    product_id: int = ProductId,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> InventoryOut:
    return _inventory(product_service.set_inventory(db, product_id, body.available))
