import uuid

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Order, User
from app.schemas.common import error_responses, page_count
from app.schemas.order import OrderCreate, OrderOut, OrderPage
from app.services import orders as order_service
from app.services.rules import OrderLine

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderOut,
    status_code=201,
    summary="Place an order",
    responses={
        200: {
            "model": OrderOut,
            "description": "Idempotent replay of an earlier identical request",
        },
        **error_responses(400, 401, 409, 422),
    },
)
def create_order(
    body: OrderCreate,
    response: Response,
    idempotency_key: str | None = Header(
        None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Optional. Repeating a request with the same key returns the original order.",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Order:
    lines = [OrderLine(item.product_id, item.quantity) for item in body.items]
    # Looked up through the module so the opt-in defect lab can substitute an implementation.
    placed = order_service.create_order(db, user, lines, idempotency_key)
    if placed.replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    response.headers["Location"] = f"/api/v1/orders/{placed.order.id}"
    return placed.order


@router.get(
    "",
    response_model=OrderPage,
    summary="Order history for the current user, newest first",
    responses=error_responses(401, 422),
)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderPage:
    rows, total = order_service.list_orders(db, user, page, page_size)
    return OrderPage(
        items=[OrderOut.model_validate(o) for o in rows],
        page=page,
        page_size=page_size,
        total=total,
        pages=page_count(total, page_size),
    )


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    summary="Get one of your orders",
    responses=error_responses(401, 404, 422),
)
def get_order(
    order_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Order:
    return order_service.get_order(db, user, order_id)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderOut,
    summary="Cancel a confirmed order and restore its inventory",
    responses=error_responses(401, 404, 409, 422),
)
def cancel_order(
    order_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Order:
    return order_service.cancel_order(db, user, order_id)
