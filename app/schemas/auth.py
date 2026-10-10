from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import StrictModel

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(StrictModel):
    email: str = Field(
        max_length=254, pattern=EMAIL_PATTERN, examples=["customer@qa-commerce.test"]
    )
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: Literal["customer", "admin"]
    customer_ref: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_at: datetime
    user: UserOut


class UserCreate(StrictModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["customer", "admin"] = "customer"
