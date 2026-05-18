"""Database engine configuration helpers."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from fitness_tracker.config import Config

DEFAULT_DATABASE_URL = Config.database_url


def get_database_url(default: str = DEFAULT_DATABASE_URL) -> str:
    """Return the configured SQLAlchemy database URL.

    Args:
        default (str): Fallback URL when ``DATABASE_URL`` is unset.

    Returns:
        str: SQLAlchemy database URL.
    """
    load_dotenv()
    return os.environ.get("DATABASE_URL", default)


def create_database_engine(url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured database.

    Args:
        url (str | None): Explicit SQLAlchemy URL. Uses ``DATABASE_URL`` when omitted.

    Returns:
        Engine: SQLAlchemy engine.
    """
    return create_engine(url or get_database_url())
