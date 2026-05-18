"""Tests for Hevy -> True Coach workout-item sync repair paths."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from fitness_tracker.apis.hevy_app.types import Set as HevySet
from fitness_tracker.apis.true_coach.exceptions import TrueCoachAPIError
from fitness_tracker.apis.true_coach.types import Workout, WorkoutItem
from fitness_tracker.database.models.hevy_app import (
    HevyAppExercise,
    HevyAppSets,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.models.tracker import (
    Exercise,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem
from fitness_tracker.sync.hevy_true_coach.sync import HevyToTrueCoachSyncronizer


def _ts() -> datetime:
    return datetime(2026, 4, 8, tzinfo=UTC)


def test_should_skip_hevy_workout_when_true_coach_workout_is_missing(store) -> None:
    """Manual Hevy workouts without a True Coach link should not abort the sync run."""
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppWorkout(
                id="manual-hevy-workout",
                title="Manual workout",
                description="Created directly in Hevy",
                start_time=_ts(),
                end_time=_ts(),
                created_at=_ts(),
                updated_at=_ts(),
            )
        )

    target = MagicMock()
    syncer = HevyToTrueCoachSyncronizer(store=store, target=target)

    syncer.sync_workout("manual-hevy-workout")

    target.workouts.update_workout_item.assert_not_called()
    target.workouts.mark_as_completed.assert_not_called()


def test_should_refresh_stale_true_coach_item_on_404_and_continue(store) -> None:  # noqa: PLR0915
    """A missing remote item should trigger local refresh instead of aborting the run."""
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppExercise(
                id="hevy-a", name="First", type="reps_only", equipment="body", default=True
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-b", name="Second", type="reps_only", equipment="body", default=True
            )
        )

        uow.session.add(Exercise(name="First", hevy_app_id="hevy-a"))
        uow.session.add(Exercise(name="Second", hevy_app_id="hevy-b"))
        uow.session.flush()

        ex_first = uow.session.get(Exercise, name="First")
        ex_second = uow.session.get(Exercise, name="Second")
        assert ex_first is not None
        assert ex_second is not None

        uow.session.add(
            TrueCoachWorkout(
                id=100,
                title="Active Recovery",
                due=_ts(),
                short_description="",
                state="pending",
                rest_day=False,
                created_at=_ts(),
                updated_at=_ts(),
            )
        )
        uow.session.add(
            HevyAppWorkout(
                id="hevy-workout-1",
                title="08 Apr 2026\nActive Recovery\n100",
                description="",
                start_time=_ts(),
                end_time=_ts(),
                created_at=_ts(),
                updated_at=_ts(),
            )
        )
        uow.session.flush()

        uow.session.add(
            TrackerWorkout(
                title="Active Recovery",
                description="",
                hevy_app_id="hevy-workout-1",
                true_coach_id=100,
            )
        )
        uow.session.flush()
        tracker_workout = uow.session.get(TrackerWorkout, true_coach_id=100)
        assert tracker_workout is not None

        uow.session.add(
            HevyAppWorkoutItem(
                workout_id="hevy-workout-1",
                index=0,
                name="First",
                notes="",
                superset_id=None,
                exercise_id="hevy-a",
            )
        )
        uow.session.add(
            HevyAppWorkoutItem(
                workout_id="hevy-workout-1",
                index=1,
                name="Second",
                notes="",
                superset_id=None,
                exercise_id="hevy-b",
            )
        )
        uow.session.flush()

        first_item = uow.session.get(HevyAppWorkoutItem, workout_id="hevy-workout-1", index=0)
        second_item = uow.session.get(HevyAppWorkoutItem, workout_id="hevy-workout-1", index=1)
        assert first_item is not None
        assert second_item is not None

        uow.session.add(HevyAppSets(workout_item_id=first_item.id, index=0, type="normal", reps=10))
        uow.session.add(HevyAppSets(workout_item_id=second_item.id, index=0, type="normal", reps=8))

        uow.session.add(
            TrueCoachWorkoutItem(
                id=500,
                workout_id=100,
                name="Removed Item",
                info="",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=None,
                assessment_id=None,
            )
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=502,
                workout_id=100,
                name="Second",
                info="",
                comment="",
                is_circuit=False,
                state="pending",
                position=2,
                exercise_id=None,
                assessment_id=None,
            )
        )
        uow.session.flush()

        uow.session.add(
            TrackerWorkoutItem(
                workout_id=tracker_workout.id,
                position=1,
                exercise_id=ex_first.id,
                hevy_app_id=first_item.id,
                true_coach_id=500,
                rest=90,
            )
        )
        uow.session.add(
            TrackerWorkoutItem(
                workout_id=tracker_workout.id,
                position=2,
                exercise_id=ex_second.id,
                hevy_app_id=second_item.id,
                true_coach_id=502,
                rest=90,
            )
        )

    refreshed_workout = Workout(
        id=100,
        due="2026-04-08",
        short_description="",
        created_at="2026-04-08T00:00:00.000000Z",
        updated_at="2026-04-08T00:10:00.000000Z",
        title="Active Recovery",
        state="missed",
        rest_day=False,
        rest_day_instructions="",
        warmup=None,
        warmup_selected_exercises=[],
        cooldown_selected_exercises=[],
        cooldown=None,
        position=None,
        order=1,
        uuid="uuid-100",
        program_name=None,
        hidden=False,
        edit_client_workout=True,
        client_id=2876143,
        comment_ids=[],
        note_id=None,
        program_id=None,
        workout_item_ids=[502],
    )
    refreshed_item = WorkoutItem(
        id=502,
        workout_id=100,
        name="Second",
        info="",
        result="",
        is_circuit=False,
        state="pending",
        selected_exercises=[],
        linked=False,
        position=2,
        assessment_id=None,
        created_at="2026-04-08T00:00:00.000000Z",
        attachments=[],
        exercise_id=None,
        request_video=False,
    )

    target = MagicMock()
    target.workouts.update_workout_item.side_effect = [
        TrueCoachAPIError("missing", status_code=404, url="workout_items/500"),
        None,
    ]
    target.workouts.get.return_value = SimpleNamespace(
        workouts=[refreshed_workout],
        workout_items=[refreshed_item],
        meta=SimpleNamespace(total_pages=1),
    )

    syncer = HevyToTrueCoachSyncronizer(store=store, target=target)
    syncer.sync_workout("hevy-workout-1")

    called_ids = [call.args[0] for call in target.workouts.update_workout_item.call_args_list]
    assert called_ids == [500, 502]
    target.workouts.mark_as_completed.assert_called_once_with(100)
