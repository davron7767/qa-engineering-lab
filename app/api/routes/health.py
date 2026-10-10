from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]
    version: str
    environment: str


@router.get("/live", response_model=LivenessResponse, summary="Liveness probe")
def live() -> LivenessResponse:
    """The process is up. Does not touch the database."""
    return LivenessResponse(status="ok")


@router.get(
    "",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "Database unreachable"}},
)
def ready(db: Session = Depends(get_db)) -> ReadinessResponse | JSONResponse:
    """The application can serve traffic: the database answers a trivial query."""
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unavailable"
    body = ReadinessResponse(
        status="ok" if database == "ok" else "unavailable",
        database=database,
        version=settings.app_version,
        environment=settings.app_env,
    )
    if database != "ok":
        return JSONResponse(body.model_dump(), status_code=503)
    return body
