"""Deterministic, idempotent seed data (synthetic only).

Records are keyed by natural keys (e-mail, SKU), never by numeric id. Running the seed again
inserts whatever is missing and leaves existing rows untouched, so it is safe on startup.
A full reset to exactly these values is done by `python -m app.db.reset` (test databases only).

Usage: python -m app.db.seed
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Product, User
from app.security import hash_password


@dataclass(frozen=True)
class SeedUser:
    email: str
    full_name: str
    role: str
    customer_ref: str


@dataclass(frozen=True)
class SeedProduct:
    sku: str
    name: str
    description: str
    price: Decimal
    inventory: int
    is_active: bool = True


SEED_USERS = (
    SeedUser("admin@qa-commerce.test", "Ada Admin", "admin", "CUST-000001"),
    SeedUser("customer@qa-commerce.test", "Casey Customer", "customer", "CUST-000002"),
    SeedUser("customer2@qa-commerce.test", "Morgan Second", "customer", "CUST-000003"),
)

SEED_PRODUCTS = (
    SeedProduct(
        "QA-KB-001",
        "Mechanical Keyboard",
        "Tenkeyless, hot-swappable switches.",
        Decimal("89.99"),
        25,
    ),
    SeedProduct("QA-MS-002", "Wireless Mouse", "Ergonomic 2.4 GHz mouse.", Decimal("29.99"), 50),
    SeedProduct(
        "QA-MN-003", "27-inch Monitor", "1440p IPS panel. Low stock.", Decimal("249.00"), 3
    ),
    SeedProduct(
        "QA-HB-004", "USB-C Hub", "7-in-1 hub. Currently out of stock.", Decimal("39.95"), 0
    ),
    SeedProduct(
        "QA-CT-005", "Cable Ties (10 pack)", "Reusable hook-and-loop ties.", Decimal("0.29"), 1000
    ),
    SeedProduct(
        "QA-WC-006", "HD Webcam", "1080p webcam with privacy shutter.", Decimal("59.50"), 10
    ),
    SeedProduct(
        "QA-LS-007",
        "Laptop Stand (Discontinued)",
        "Aluminium stand. No longer sold.",
        Decimal("45.00"),
        12,
        is_active=False,
    ),
)


def _password_for(role: str) -> str:
    settings = get_settings()
    return settings.seed_admin_password if role == "admin" else settings.seed_customer_password


def seed_session(db: Session) -> dict[str, int]:
    """Insert missing seed records using an existing session. Returns counts inserted."""
    inserted = {"users": 0, "products": 0}
    existing_emails = set(db.scalars(select(User.email)))
    for u in SEED_USERS:
        if u.email not in existing_emails:
            db.add(
                User(
                    email=u.email,
                    full_name=u.full_name,
                    role=u.role,
                    customer_ref=u.customer_ref,
                    password_hash=hash_password(_password_for(u.role)),
                )
            )
            inserted["users"] += 1
    existing_skus = set(db.scalars(select(Product.sku)))
    for p in SEED_PRODUCTS:
        if p.sku not in existing_skus:
            db.add(
                Product(
                    sku=p.sku,
                    name=p.name,
                    description=p.description,
                    price=p.price,
                    inventory=p.inventory,
                    is_active=p.is_active,
                )
            )
            inserted["products"] += 1
    db.commit()
    return inserted


def seed(session_factory: sessionmaker[Session] | None = None) -> dict[str, int]:
    if session_factory is None:
        from app.db.session import get_session_factory

        session_factory = get_session_factory()
    with session_factory() as db:
        return seed_session(db)


if __name__ == "__main__":
    print(f"Seed complete: inserted {seed()}")
