"""Password hashing, opaque session tokens and CSRF tokens."""

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
# Verified against when the e-mail is unknown, so both failure paths cost the same time.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(secret_key: str, session_token: str) -> str:
    """CSRF token bound to the session: forging it requires both the cookie and the server key."""
    return hmac.new(secret_key.encode(), session_token.encode(), hashlib.sha256).hexdigest()


def csrf_valid(secret_key: str, session_token: str, submitted: str | None) -> bool:
    return bool(submitted) and hmac.compare_digest(
        csrf_token(secret_key, session_token), submitted or ""
    )
