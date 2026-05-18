"""Generic CRUD operations via the Tx."""

from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.apple_health import AppleHealthWorkoutType
from fitness_tracker.database.store import Store


def test_add_and_get(store: Store) -> None:
    """Verify a row added inside a UoW is readable after commit.

    Args:
        store (Store): In-memory store fixture.
    """
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppExercise(
                id="ex1",
                name="Bench Press",
                type="weight",
                equipment="barbell",
                default=True,
            )
        )

    result = store.query_one(HevyAppExercise, id="ex1")
    assert result is not None
    assert result.name == "Bench Press"


def test_merge_updates(store: Store) -> None:
    """Verify merging an existing row updates it rather than duplicating.

    Args:
        store (Store): In-memory store fixture.
    """
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppExercise(
                id="ex2",
                name="Squat",
                type="weight",
                equipment="barbell",
                default=True,
            )
        )

    with store.unit_of_work() as uow:
        uow.session.merge(
            HevyAppExercise(
                id="ex2",
                name="Back Squat",
                type="weight",
                equipment="barbell",
                default=True,
            )
        )

    result = store.query_one(HevyAppExercise, id="ex2")
    assert result is not None
    assert result.name == "Back Squat"


def test_delete(store: Store) -> None:
    """Verify deleting a row removes it from the database.

    Args:
        store (Store): In-memory store fixture.
    """
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppExercise(
                id="ex3",
                name="Deadlift",
                type="weight",
                equipment="barbell",
                default=True,
            )
        )

    with store.unit_of_work() as uow:
        row = uow.session.get(HevyAppExercise, id="ex3")
        assert row is not None
        uow.session.delete(row)

    assert store.query_one(HevyAppExercise, id="ex3") is None


def test_get_all(store: Store) -> None:
    """Verify get_all returns all matching rows.

    Args:
        store (Store): In-memory store fixture.
    """
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppExercise(
                id="a1",
                name="Curl",
                type="weight",
                equipment="dumbbell",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="a2",
                name="Press",
                type="weight",
                equipment="dumbbell",
                default=True,
            )
        )

    with store.unit_of_work() as uow:
        results = uow.session.get_all(HevyAppExercise, equipment="dumbbell")
        assert len(results) == 2


def test_insert_values_omits_unset_autoincrement_primary_key() -> None:
    """Verify PostgreSQL can use the sequence for generated primary keys."""
    values = AppleHealthWorkoutType(name="Outdoor Walk").insert_values()

    assert values == {"name": "Outdoor Walk"}
