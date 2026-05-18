"""Tests for True Coach -> tracker snapshot import."""

from unittest.mock import MagicMock

from fitness_tracker.apis.true_coach.types import Meta, Workout, WorkoutItem, WorkoutResponse
from fitness_tracker.database.models.true_coach import TrueCoachExercise, TrueCoachWorkoutItem
from fitness_tracker.database.store import Store
from fitness_tracker.sync.true_coach_tracker.sync import TrueCoachToFitnessTrackerSyncronizer


def _workout() -> Workout:
    return Workout(
        id=599821297,
        due="2026-05-18",
        short_description="",
        created_at="2026-05-18T00:00:00.000000Z",
        updated_at="2026-05-18T00:10:00.000000Z",
        title="Mobility",
        state="pending",
        rest_day=False,
        rest_day_instructions="",
        warmup=None,
        warmup_selected_exercises=[],
        cooldown_selected_exercises=[],
        cooldown=None,
        position=None,
        order=1,
        uuid="uuid-599821297",
        program_name=None,
        hidden=False,
        edit_client_workout=True,
        client_id=2876143,
        comment_ids=[],
        note_id=None,
        program_id=None,
        workout_item_ids=[-1393788898],
    )


def _workout_item() -> WorkoutItem:
    return WorkoutItem(
        id=-1393788898,
        workout_id=599821297,
        name="Hip Adductor Med Ball Squeeze",
        info="2 x 2 with an 8s squeeze",
        result="",
        is_circuit=False,
        state="pending",
        selected_exercises=[],
        linked=False,
        position=8,
        assessment_id=None,
        created_at="2026-05-18T00:00:00.000000Z",
        attachments=[],
        exercise_id=16369167,
        request_video=False,
    )


def test_sync_workouts_creates_referenced_exercise_before_workout_item(store: Store) -> None:
    """A workout item with an exercise FK must not reference a missing exercise row."""
    response = WorkoutResponse(
        workouts=[_workout()],
        workout_items=[_workout_item()],
        comments=[],
        meta=Meta(page=1, total_pages=1, per_page=10, total_count=1),
    )
    syncer = TrueCoachToFitnessTrackerSyncronizer(store=store, source=MagicMock())

    syncer.sync_workouts(response)

    exercise = store.query_one(TrueCoachExercise, id=16369167)
    item = store.query_one(TrueCoachWorkoutItem, id=-1393788898)
    assert exercise is not None
    assert exercise.name == "Hip Adductor Med Ball Squeeze"
    assert item is not None
    assert item.exercise_id == exercise.id
