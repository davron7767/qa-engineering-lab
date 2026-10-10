"""Application configuration loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRET = "local-dev-only-change-me-0123456789abcdef"

DefectMode = Literal[
    "",
    "wrong_total",
    "inventory_before_validation",
    "persist_rejected_order",
    "oversell_race",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "1.0.0"
    database_url: str = (
        "postgresql+psycopg://qa_commerce:qa_commerce_local@localhost:5433/qa_commerce"
    )
    # Only used by the backend integration tests and `python -m app.db.reset`.
    test_database_url: str | None = None
    secret_key: str = Field(default=PLACEHOLDER_SECRET, min_length=32)
    session_ttl_minutes: int = Field(default=60, ge=1, le=24 * 60)
    cookie_secure: bool = False

    seed_on_startup: bool = True
    seed_admin_password: str = "Admin#Local2024"
    seed_customer_password: str = "Customer#Local2024"

    enable_test_hooks: bool = False
    defect_mode: DefectMode = ""

    @model_validator(mode="after")
    def _guard_production(self) -> "Settings":
        if self.app_env == "production":
            if self.secret_key == PLACEHOLDER_SECRET:
                raise ValueError("SECRET_KEY must be changed when APP_ENV=production")
            if self.defect_mode:
                raise ValueError("DEFECT_MODE cannot be enabled when APP_ENV=production")
        return self

    @property
    def test_hooks_active(self) -> bool:
        return self.enable_test_hooks and self.app_env != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
