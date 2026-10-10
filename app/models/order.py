import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

ORDER_STATUSES = ("confirmed", "cancelled")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('confirmed', 'cancelled')", name="status_valid"),
        CheckConstraint("total >= 0", name="total_non_negative"),
        # One order per (user, idempotency key): the database is the final arbiter for
        # concurrent duplicate submissions.
        UniqueConstraint("user_id", "idempotency_key", name="uq_orders_user_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    customer_ref: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
        lazy="selectin",
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price > 0", name="unit_price_positive"),
        UniqueConstraint("order_id", "product_id", name="uq_order_items_order_product"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    # Snapshots: the order keeps the name/SKU/price that were valid when it was placed.
    sku: Mapped[str] = mapped_column(String(32))
    product_name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    order: Mapped[Order] = relationship(back_populates="items")
