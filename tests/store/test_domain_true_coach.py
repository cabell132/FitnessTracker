"""Smoke tests for True Coach tag deduplication on UnitOfWork."""

from fitness_tracker.database.models.true_coach import TrueCoachTag
from fitness_tracker.database.store import Store


def test_ensure_tags_creates_and_reuses(store: Store) -> None:
    """Verify tags are created once and reused on repeated calls.

    Args:
        store (Store): In-memory store fixture.
    """
    with store.unit_of_work() as uow:
        uow._tc_ensure_tags(exercise_id=1, tags=["push", "push"], category="pattern")

    results = store.query_all(TrueCoachTag, category="pattern")
    assert len(results) == 1
    assert results[0].name == "push"
