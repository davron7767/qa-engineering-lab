"""Programmatic Alembic access so the app and test fixtures use the same migration path."""

from pathlib import Path

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    if database_url:
        config.attributes["database_url"] = database_url
    return config


def upgrade_to_head(database_url: str | None = None) -> None:
    command.upgrade(alembic_config(database_url), "head")
