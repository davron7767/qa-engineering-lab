import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AuthenticationRequired, DuplicateEmail, InvalidCredentials
from app.models import AuthSession, User
from app.security import hash_password, hash_token, new_session_token, verify_password


class InvalidToken(AuthenticationRequired):
    code = "INVALID_TOKEN"


@dataclass(frozen=True)
class IssuedSession:
    token: str
    expires_at: datetime
    user: User


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    # verify_password runs even for unknown e-mails, so timing does not reveal which accounts exist.
    if not verify_password(password, user.password_hash if user else None) or user is None:
        raise InvalidCredentials("Invalid email or password")
    return user


def issue_session(db: Session, user: User) -> IssuedSession:
    token = new_session_token()
    expires_at = datetime.now(UTC) + timedelta(minutes=get_settings().session_ttl_minutes)
    db.add(AuthSession(user_id=user.id, token_hash=hash_token(token), expires_at=expires_at))
    db.commit()
    return IssuedSession(token=token, expires_at=expires_at, user=user)


def resolve_session(db: Session, token: str) -> AuthSession:
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if session is None or session.revoked_at is not None:
        raise InvalidToken("Session token is invalid or has been revoked")
    if session.expires_at <= datetime.now(UTC):
        raise InvalidToken("Session token has expired")
    return session


def revoke_session(db: Session, token: str) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.token_hash == hash_token(token), AuthSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    db.commit()


def random_customer_ref() -> str:
    # Seeded users have fixed refs (CUST-0000xx); created users get random 6-digit refs.
    # Uniqueness is enforced by the database; a collision simply triggers a retry.
    return f"CUST-{secrets.randbelow(900_000) + 100_000}"


def create_user(db: Session, email: str, full_name: str, password: str, role: str) -> User:
    normalized = email.strip().lower()
    if db.scalar(select(User.id).where(User.email == normalized)) is not None:
        raise DuplicateEmail("A user with this email already exists")
    for _attempt in range(5):
        user = User(
            email=normalized,
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
            customer_ref=random_customer_ref(),
        )
        db.add(user)
        try:
            db.commit()
            return user
        except IntegrityError as exc:
            db.rollback()
            if "uq_users_email" in str(exc.orig):
                raise DuplicateEmail("A user with this email already exists") from exc
            # customer_ref collision: retry with a fresh number.
    raise RuntimeError("could not allocate a customer reference")
