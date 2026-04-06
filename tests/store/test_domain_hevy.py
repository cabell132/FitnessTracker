"""Smoke tests for Hevy domain helpers on UnitOfWork."""

from datetime import datetime

from fitness_tracker.database.models.hevy_app import HevyAppWorkout
from fitness_tracker.database.store import Store


def test_hevy_get_workout_returns_none(store: Store) -> None:
    """Verify returns None when no workout exists.

    Args:
        store (Store): In-memory store fixture.
    """
    with store.unit_of_work() as uow:
        assert uow.hevy_get_workout(id="missing") is None


def test_hevy_get_placeholders_empty(store: Store) -> None:
    """Verify returns empty list when no placeholders exist.

    Args:
        store (Store): In-memory store fixture.
    """
    with store.unit_of_work() as uow:
        assert uow.hevy_get_placeholders() == []


def test_hevy_add_and_delete_workout(store: Store) -> None:
    """Verify insert and delete of a bare workout row.

    Args:
        store (Store): In-memory store fixture.
    """
    dt = datetime(2025, 1, 1, 10, 0, 0)  # noqa: DTZ001
    with store.unit_of_work() as uow:
        uow.merge(
            HevyAppWorkout(
                id="w1",
                title="Push Day",
                description="",
                start_time=dt,
                end_time=datetime(2025, 1, 1, 11, 0, 0),  # noqa: DTZ001
                created_at=dt,
                updated_at=dt,
            )
        )

    with store.unit_of_work() as uow:
        assert uow.hevy_get_workout(id="w1") is not None
        uow.hevy_delete_workout(id="w1")

    with store.unit_of_work() as uow:
        assert uow.hevy_get_workout(id="w1") is None
