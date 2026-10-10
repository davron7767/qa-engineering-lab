from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import AuthenticationRequired, Forbidden
from app.models import User
from app.services import auth as auth_service

bearer_scheme = HTTPBearer(auto_error=False, description="Token from POST /api/v1/auth/login")


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AuthenticationRequired(
            "Authentication required: send 'Authorization: Bearer <token>'"
        )
    return credentials.credentials


def get_current_user(token: str = Depends(get_bearer_token), db: Session = Depends(get_db)) -> User:
    return auth_service.resolve_session(db, token).user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise Forbidden("This operation requires the admin role")
    return user
