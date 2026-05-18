from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fitness_tracker.apis.hevy_app.types import Exercise as HevyExercisePayload
from fitness_tracker.apis.hevy_app.types import Set, Workout
from fitness_tracker.database.models import Exercise as TrackerExercise
from fitness_tracker.database.models.hevy_app import (
    HevyAppExercise,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.maintenance.hevy_exercise_migration import (
    HevyExerciseTemplateMigrationService,
    MigrationError,
)


class FakeHevyWorkouts:
    def __init__(self, workouts: dict[str, Workout]) -> None:
        self.workouts = workouts
        self.updated: list[Workout] = []

    def get_workout(self, workout_id: str) -> Workout | None:
        return self.workouts.get(workout_id)

    def update_workout(self, workout_id: str, workout: Workout) -> Workout | None:
        self.updated.append(workout)
        self.workouts[workout_id] = workout
        return workout


def test_plan_reports_counts_and_conflicts(store) -> None:
    _seed(store, include_target_in_same_workout=True)
    service = HevyExerciseTemplateMigrationService(store)

    plan = service.plan("source", "target")

    assert plan.affected_items == 2
    assert plan.affected_workouts == 2
    assert plan.target_existing_items == 1
    assert plan.target_existing_workouts == 1
    assert len(plan.conflicts) == 1
    assert plan.conflicts[0].workout_id == "w1"


def test_plan_rejects_type_or_equipment_mismatch_without_force(store) -> None:
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppExercise(
                id="source", name="Source", type="weight_reps", equipment="machine", default=False
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="target", name="Target", type="duration", equipment="machine", default=True
            )
        )
    service = HevyExerciseTemplateMigrationService(store)

    with pytest.raises(MigrationError, match="type/equipment differ"):
        service.plan("source", "target")


def test_apply_updates_hevy_first_then_local_rows(store) -> None:
    _seed(store, include_target_in_same_workout=False)
    fake = FakeHevyWorkouts(
        {
            "w1": _api_workout("w1", ["source"]),
            "w2": _api_workout("w2", ["source"]),
        }
    )
    service = HevyExerciseTemplateMigrationService(store, fake)

    result = service.apply("source", "target", backup_path=None, report_path=None)

    assert len(fake.updated) == 2
    assert all(
        exercise.exercise_template_id == "target"
        for workout in fake.updated
        for exercise in workout.exercises
    )
    assert result.db_workout_items_updated == 2
    with store.unit_of_work() as uow:
        assert uow.session.get_all(HevyAppWorkoutItem, exercise_id="source") == []
        target_items = uow.session.get_all(HevyAppWorkoutItem, exercise_id="target")
        assert len(target_items) == 2
        assert {item.name for item in target_items} == {"Target"}
        tracker = uow.session.get(TrackerExercise, id=7)
        assert tracker.hevy_app_id == "target"
        assert tracker.name == "Target"


def test_apply_continues_when_remote_workout_is_already_migrated(store) -> None:
    _seed(store, include_target_in_same_workout=False)
    fake = FakeHevyWorkouts(
        {
            "w1": _api_workout("w1", ["target"]),
            "w2": _api_workout("w2", ["source"]),
        }
    )
    service = HevyExerciseTemplateMigrationService(store, fake)

    result = service.apply("source", "target", backup_path=None, report_path=None)

    assert [item.replaced_exercises for item in result.api_updates] == [0, 1]
    assert len(fake.updated) == 1
    with store.unit_of_work() as uow:
        assert uow.session.get_all(HevyAppWorkoutItem, exercise_id="source") == []


def _seed(store, *, include_target_in_same_workout: bool) -> None:
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppExercise(
                id="source", name="Source", type="weight_reps", equipment="machine", default=False
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="target", name="Target", type="weight_reps", equipment="machine", default=True
            )
        )
        uow.session.add(
            TrackerExercise(id=7, name="Source", hevy_app_id="source", true_coach_id=123)
        )
        uow.session.add(
            HevyAppWorkout(
                id="w1",
                title="Workout 1",
                description="",
                start_time=datetime(2026, 1, 1, tzinfo=UTC),
                end_time=datetime(2026, 1, 1, 1, tzinfo=UTC),
            )
        )
        uow.session.add(
            HevyAppWorkout(
                id="w2",
                title="Workout 2",
                description="",
                start_time=datetime(2026, 1, 2, tzinfo=UTC),
                end_time=datetime(2026, 1, 2, 1, tzinfo=UTC),
            )
        )
        uow.session.add(
            HevyAppWorkoutItem(
                workout_id="w1", index=0, name="Source", notes="", exercise_id="source"
            )
        )
        uow.session.add(
            HevyAppWorkoutItem(
                workout_id="w2", index=0, name="Source", notes="", exercise_id="source"
            )
        )
        if include_target_in_same_workout:
            uow.session.add(
                HevyAppWorkoutItem(
                    workout_id="w1", index=1, name="Target", notes="", exercise_id="target"
                )
            )


def _api_workout(workout_id: str, exercise_ids: list[str]) -> Workout:
    return Workout(
        id=workout_id,
        title="Workout",
        description="",
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-01T01:00:00Z",
        updated_at="2026-01-01T01:00:00Z",
        created_at="2026-01-01T00:00:00Z",
        exercises=[
            HevyExercisePayload(
                index=index,
                title=exercise_id,
                notes="",
                exercise_template_id=exercise_id,
                superset_id=None,
                sets=[
                    Set(
                        index=0,
                        type="normal",
                        weight_kg=10,
                        reps=10,
                        distance_meters=None,
                        duration_seconds=None,
                        rpe=None,
                    )
                ],
            )
            for index, exercise_id in enumerate(exercise_ids)
        ],
    )
