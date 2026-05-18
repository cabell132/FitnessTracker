"""Smoke tests for Hevy domain helpers on UnitOfWork."""

from datetime import datetime

from fitness_tracker.apis.hevy_app.types import Exercise as HevyExercisePayload
from fitness_tracker.database.models.hevy_app import HevyAppExercise, HevyAppWorkout, HevyAppWorkoutItem
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


def test_hevy_add_workout_item_normalizes_false_superset_id(store: Store) -> None:
    """Verify Hevy's false superset sentinel is stored as no superset."""
    dt = datetime(2026, 5, 18, 6, 0, 0)  # noqa: DTZ001
    with store.unit_of_work() as uow:
        uow.add(
            HevyAppExercise(
                id="template-1",
                name="Incline Treadmill Walk",
                type="duration",
                equipment="treadmill",
                default=True,
            )
        )
        uow.add(
            HevyAppWorkout(
                id="workout-1",
                title="Workout",
                description="",
                start_time=dt,
                end_time=dt,
                created_at=dt,
                updated_at=dt,
            )
        )
        uow.hevy_add_workout_item(
            workout_id="workout-1",
            exercise=HevyExercisePayload(
                index=8,
                title="Incline Treadmill Walk",
                notes="",
                superset_id=False,  # type: ignore[arg-type]
                exercise_template_id="template-1",
                sets=[],
            ),
        )

    item = store.query_one(HevyAppWorkoutItem, workout_id="workout-1", index=8)
    assert item is not None
    assert item.superset_id is None


def test_hevy_add_workout_normalizes_optional_text_fields(store: Store) -> None:
    """Verify nullable API text fields fit non-null local columns."""
    from fitness_tracker.apis.hevy_app.types import Workout as HevyWorkoutPayload

    with store.unit_of_work() as uow:
        uow.add(
            HevyAppExercise(
                id="template-2",
                name="Bench Press",
                type="weight",
                equipment="barbell",
                default=True,
            )
        )
        uow.hevy_add_workout(
            HevyWorkoutPayload(
                id="workout-2",
                title="Bench Day",
                description=None,
                start_time="2026-05-18T06:00:00Z",
                end_time="2026-05-18T07:00:00Z",
                created_at="2026-05-18T06:00:00Z",
                updated_at="2026-05-18T07:00:00Z",
                exercises=[
                    HevyExercisePayload(
                        index=0,
                        title="Bench Press",
                        notes=None,
                        exercise_template_id="template-2",
                        sets=[],
                    )
                ],
            )
        )

    workout = store.query_one(HevyAppWorkout, id="workout-2")
    item = store.query_one(HevyAppWorkoutItem, workout_id="workout-2", index=0)
    assert workout is not None
    assert workout.description == ""
    assert item is not None
    assert item.notes == ""
