from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_bearer_token, get_current_user, require_admin
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse, UserCreate, UserOut
from app.schemas.common import error_responses
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    summary="Exchange email and password for a bearer token",
    responses=error_responses(401, 422),
)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = auth_service.authenticate(db, body.email, body.password)
    issued = auth_service.issue_session(db, user)
    return LoginResponse(
        access_token=issued.token,
        expires_at=issued.expires_at,
        user=UserOut.model_validate(user),
    )


@router.post(
    "/auth/logout",
    status_code=204,
    summary="Revoke the current bearer token",
    responses=error_responses(401),
)
def logout(
    token: str = Depends(get_bearer_token),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    auth_service.revoke_session(db, token)
    return Response(status_code=204)


@router.get(
    "/auth/me", response_model=UserOut, summary="Current user", responses=error_responses(401)
)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post(
    "/users",
    response_model=UserOut,
    status_code=201,
    summary="Create a user (admin only)",
    responses=error_responses(401, 403, 409, 422),
)
def create_user(
    body: UserCreate, _admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> User:
    return auth_service.create_user(db, body.email, body.full_name, body.password, body.role)
