"""Transaction semantics — auto-commit and auto-rollback."""

import pytest

from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.true_coach import TrueCoachTag
from fitness_tracker.database.store import Store


def test_auto_commit_on_clean_exit(store: Store) -> None:
    """Verify data persists when the context exits without error.

    Args:
        store (Store): In-memory store fixture.
    """
    with store.unit_of_work() as uow:
        uow.add(
            HevyAppExercise(
                id="tx1",
                name="Row",
                type="weight",
                equipment="barbell",
                default=True,
            )
        )

    assert store.query_one(HevyAppExercise, id="tx1") is not None


def test_rollback_on_exception(store: Store) -> None:
    """Verify data does NOT persist when the context raises.

    Args:
        store (Store): In-memory store fixture.
    """
    with pytest.raises(RuntimeError), store.unit_of_work() as uow:  # noqa: PT012
        uow.add(
            HevyAppExercise(
                id="tx2",
                name="Fly",
                type="weight",
                equipment="cable",
                default=True,
            )
        )
        uow.flush()
        msg = "intentional"
        raise RuntimeError(msg)

    assert store.query_one(HevyAppExercise, id="tx2") is None


def test_flush_makes_ids_visible(store: Store) -> None:
    """Verify flush exposes auto-generated IDs without committing.

    Args:
        store (Store): In-memory store fixture.
    """
    with store.unit_of_work() as uow:
        tag = TrueCoachTag(name="push", category="pattern")
        uow.add(tag)
        uow.flush()
        assert tag.id is not None

    result = store.query_one(TrueCoachTag, name="push")
    assert result is not None
