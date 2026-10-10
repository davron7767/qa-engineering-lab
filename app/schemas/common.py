from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# Money is serialized as a JSON string with exactly two fractional digits ("19.90"),
# so no client ever has to parse a binary float to read a price.
Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
    Field(json_schema_extra={"type": "string", "pattern": r"^\d+\.\d{2}$", "example": "19.99"}),
]

# Accepted on input as a JSON number or numeric string; at most 2 decimal places.
PriceIn = Annotated[
    Decimal,
    Field(
        gt=Decimal("0"),
        le=Decimal("999999.99"),
        max_digits=8,
        decimal_places=2,
        examples=["19.99"],
    ),
]


class StrictModel(BaseModel):
    """Request bodies reject unknown fields: clients cannot smuggle in totals or prices."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ErrorInfo(BaseModel):
    code: str = Field(examples=["INSUFFICIENT_INVENTORY"])
    message: str
    details: list[dict[str, Any]] = []
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorInfo


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


def page_count(total: int, page_size: int) -> int:
    return (total + page_size - 1) // page_size


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse, "description": description}
    for code, description in {
        400: "Business-rule violation",
        401: "Missing, invalid, expired or revoked credentials",
        403: "Authenticated but not permitted",
        404: "Resource not found",
        409: "Conflict (inventory, idempotency, uniqueness, state)",
        422: "Request validation failed",
    }.items()
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: ERROR_RESPONSES[code] for code in codes}
