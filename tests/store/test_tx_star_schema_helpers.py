"""Tx helpers for star-schema SQL and tracker linking (GH issue 8).

Covers ``get_unlinked_*_workout_items``, ``link_workout_item_hevy_id``,
``link_metric_item_to_true_coach``, and ``update_workout_exercise_ids_from_hevy``.
"""

from datetime import datetime

from fitness_tracker.database.models.hevy_app import (
    HevyAppExercise,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.models.tracker import (
    Exercise,
    Metric,
    MetricItem,
    Workout,
    WorkoutItem,
)
from fitness_tracker.database.models.true_coach import (
    TrueCoachAssessment,
    TrueCoachWorkout,
    TrueCoachWorkoutItem,
)
from fitness_tracker.database.store import Store


def test_should_return_only_tc_items_missing_hevy_links_when_mixed_items_exist(
    store: Store,
) -> None:
    """Unlinked TC query excludes rows that already have ``hevy_app_id``."""
    dt = datetime(2025, 1, 1, 10, 0, 0)  # noqa: DTZ001
    with store.unit_of_work() as uow:
        uow.session.add(TrueCoachWorkout(id=700, title="W", state="scheduled", rest_day=False))
        uow.session.add(
            HevyAppWorkout(id="700", title="H", description="", start_time=dt, end_time=dt)
        )
        tw = Workout(title="T", true_coach_id=700, hevy_app_id="700")
        uow.session.add(tw)
        uow.session.flush()
        uow.session.add(Exercise(id=70, name="Ex", true_coach_id=None, hevy_app_id=None))
        uow.session.add(
            TrueCoachWorkoutItem(id=7001, workout_id=700, name="A", state="open", position=0)
        )
        uow.session.add(
            TrueCoachWorkoutItem(id=7002, workout_id=700, name="B", state="open", position=1)
        )
        uow.session.add(
            HevyAppWorkoutItem(
                id=8001, workout_id=700, index=0, name="B", notes="", exercise_id=None
            )
        )
        uow.session.flush()
        uow.session.add(
            WorkoutItem(
                workout_id=tw.id,
                position=0,
                exercise_id=70,
                true_coach_id=7001,
                hevy_app_id=None,
            )
        )
        uow.session.add(
            WorkoutItem(
                workout_id=tw.id,
                position=1,
                exercise_id=70,
                true_coach_id=7002,
                hevy_app_id=8001,
            )
        )

    with store.unit_of_work() as uow:
        rows = uow.cross_domain.get_unlinked_tc_workout_items(700)

    ids = {r["true_coach_id"] for r in rows}
    assert ids == {7001}, f"expected only unlinked TC item 7001, got {ids}"


def test_should_return_only_hevy_items_not_yet_on_workout_items(store: Store) -> None:
    """Unlinked Hevy query excludes ``HevyAppWorkoutItem`` ids already on ``WorkoutItem``."""
    dt = datetime(2025, 1, 2, 10, 0, 0)  # noqa: DTZ001
    with store.unit_of_work() as uow:
        uow.session.add(TrueCoachWorkout(id=701, title="W2", state="scheduled", rest_day=False))
        uow.session.add(
            HevyAppWorkout(id="701", title="H2", description="", start_time=dt, end_time=dt)
        )
        tw = Workout(title="T2", true_coach_id=701, hevy_app_id="701")
        uow.session.add(tw)
        uow.session.flush()
        uow.session.add(Exercise(id=71, name="Ex2", true_coach_id=None, hevy_app_id=None))
        uow.session.add(
            TrueCoachWorkoutItem(id=7011, workout_id=701, name="A", state="open", position=0)
        )
        uow.session.add(
            HevyAppWorkoutItem(
                id=8101, workout_id=701, index=0, name="H1", notes="", exercise_id=None
            )
        )
        uow.session.add(
            HevyAppWorkoutItem(
                id=8102, workout_id=701, index=1, name="H2", notes="", exercise_id=None
            )
        )
        uow.session.flush()
        uow.session.add(
            WorkoutItem(
                workout_id=tw.id,
                position=0,
                exercise_id=71,
                true_coach_id=7011,
                hevy_app_id=8101,
            )
        )

    with store.unit_of_work() as uow:
        rows = uow.cross_domain.get_unlinked_hevy_workout_items(701)

    ids = {r["hevy_app_id"] for r in rows}
    assert ids == {8102}, f"expected only unlinked Hevy item 8102, got {ids}"


def test_should_set_hevy_app_id_when_link_workout_item_hevy_id_called(store: Store) -> None:
    """ORM helper updates the tracker workout item FK."""
    with store.unit_of_work() as uow:
        uow.session.add(TrueCoachWorkout(id=702, title="W3", state="scheduled", rest_day=False))
        tw = Workout(title="T3", true_coach_id=702)
        uow.session.add(tw)
        uow.session.flush()
        uow.session.add(Exercise(id=72, name="E3", true_coach_id=None, hevy_app_id=None))
        uow.session.add(
            TrueCoachWorkoutItem(id=7021, workout_id=702, name="X", state="open", position=0)
        )
        uow.session.flush()
        uow.session.add(
            WorkoutItem(workout_id=tw.id, position=0, exercise_id=72, true_coach_id=7021)
        )

    with store.unit_of_work() as uow:
        uow.tracker.link_workout_item_hevy_id(true_coach_id=7021, hevy_app_id=9900)

    row = store.query_one(WorkoutItem, true_coach_id=7021)
    assert row is not None
    assert row.hevy_app_id == 9900


def test_should_noop_link_workout_item_hevy_id_when_row_missing(store: Store) -> None:
    """Missing ``WorkoutItem`` does not raise."""
    with store.unit_of_work() as uow:
        uow.tracker.link_workout_item_hevy_id(true_coach_id=999999, hevy_app_id=1)


def test_should_set_true_coach_id_on_metric_item_when_linked(store: Store) -> None:
    """Assessment sync helper writes ``MetricItem.true_coach_id``."""
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachAssessment(id=400, assessment_group_id=1, name="m", units="kg", order=0)
        )
        uow.session.add(Metric(id=500, name="weight", true_coach_id=400))
        uow.session.flush()
        uow.session.add(MetricItem(id=600, metric_id=500, value=80.0, date=datetime(2025, 3, 1)))  # noqa: DTZ001

    with store.unit_of_work() as uow:
        uow.tracker.link_metric_item_to_true_coach(metric_item_id=600, true_coach_id=9001)

    row = store.query_one(MetricItem, id=600)
    assert row is not None
    assert row.true_coach_id == 9001


def test_should_noop_link_metric_item_when_row_missing(store: Store) -> None:
    """Missing ``MetricItem`` does not raise."""
    with store.unit_of_work() as uow:
        uow.tracker.link_metric_item_to_true_coach(metric_item_id=999999, true_coach_id=1)


def _seed_workout_item_exercise_update_scenario(store: Store) -> None:
    """Insert workout, items, and exercises for ``update_workout_exercise_ids_from_hevy``."""
    dt = datetime(2025, 1, 3, 10, 0, 0)  # noqa: DTZ001
    with store.unit_of_work() as uow:
        uow.session.add(TrueCoachWorkout(id=703, title="W4", state="scheduled", rest_day=False))
        uow.session.add(
            HevyAppWorkout(id="703", title="H4", description="", start_time=dt, end_time=dt)
        )
        uow.session.add(
            HevyAppExercise(id="hex99", name="Pull", type="w", equipment="bar", default=False)
        )
        tw = Workout(title="T4", true_coach_id=703, hevy_app_id="703")
        uow.session.add(tw)
        uow.session.flush()
        uow.session.add(Exercise(id=73, name="Wrong", true_coach_id=None, hevy_app_id=None))
        uow.session.add(Exercise(id=74, name="Right", true_coach_id=None, hevy_app_id="hex99"))
        uow.session.add(
            TrueCoachWorkoutItem(id=7031, workout_id=703, name="Item", state="open", position=0)
        )
        uow.session.add(
            HevyAppWorkoutItem(
                id=8200,
                workout_id=703,
                index=0,
                name="Item",
                notes="",
                exercise_id="hex99",
            )
        )
        uow.session.flush()
        uow.session.add(
            WorkoutItem(
                workout_id=tw.id,
                position=0,
                exercise_id=73,
                true_coach_id=7031,
                hevy_app_id=8200,
            )
        )


def test_should_update_workout_item_exercise_ids_from_hevy_links(store: Store) -> None:
    """SQL helper propagates tracker ``Exercise.id`` from Hevy exercise FKs."""
    _seed_workout_item_exercise_update_scenario(store)
    with store.unit_of_work() as uow:
        uow.cross_domain.update_workout_exercise_ids_from_hevy(703)

    row = store.query_one(WorkoutItem, true_coach_id=7031)
    assert row is not None
    assert row.exercise_id == 74
