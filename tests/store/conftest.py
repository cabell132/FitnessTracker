"""Shared fixtures for Store / UnitOfWork boundary tests."""

import pytest
from sqlalchemy import create_engine

from fitness_tracker.database.store import Store


@pytest.fixture
def store() -> Store:
    """Create a Store backed by an in-memory SQLite database with all tables.

    Returns:
        Store: Ready-to-use store instance.
    """
    engine = create_engine("sqlite:///:memory:")
    s = Store(engine)
    s.init_db()
    return s
