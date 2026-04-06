"""Store lifecycle tests — init_db and drop_tables."""

from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.store import Store


def test_init_creates_tables(store: Store) -> None:
    """Verify tables exist after init_db and return empty results.

    Args:
        store (Store): In-memory store fixture.
    """
    result = store.query_all(HevyAppExercise)
    assert result == []


def test_drop_and_reinit(store: Store) -> None:
    """Verify tables can be dropped and recreated without error.

    Args:
        store (Store): In-memory store fixture.
    """
    store.drop_tables()
    store.init_db()
    result = store.query_all(HevyAppExercise)
    assert result == []
