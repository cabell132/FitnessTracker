"""Tests for True Coach snapshot import and scale weight chart sync."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from fitness_tracker.apis.true_coach.types import (
    Assessment,
    AssessmentItem,
    AssessmentResponse,
    Meta,
    Workout,
    WorkoutItem,
    WorkoutResponse,
)
from fitness_tracker.database.models.tracker import Workout as TrackerWorkout
from fitness_tracker.database.models.tracker import WorkoutItem as TrackerWorkoutItem
from fitness_tracker.database.models.true_coach import TrueCoachExercise, TrueCoachWorkoutItem
from fitness_tracker.database.models.vesync import VeSyncWeighIn
from fitness_tracker.database.store import Store
from fitness_tracker.sync.tracker_true_coach.sync import TrackerToTrueCoachSyncronizer
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


def test_sync_workouts_creates_tracker_workout_and_items_for_result_sync_linking(
    store: Store,
) -> None:
    """Imported True Coach snapshots create tracker hub rows before Hevy result sync."""
    response = WorkoutResponse(
        workouts=[_workout()],
        workout_items=[_workout_item()],
        comments=[],
        meta=Meta(page=1, total_pages=1, per_page=10, total_count=1),
    )
    syncer = TrueCoachToFitnessTrackerSyncronizer(store=store, source=MagicMock())

    syncer.sync_workouts(response)

    tracker_workout = store.query_one(TrackerWorkout, true_coach_id=599821297)
    assert tracker_workout is not None
    assert tracker_workout.title == "Mobility"
    assert tracker_workout.hevy_app_id is None

    tracker_item = store.query_one(TrackerWorkoutItem, true_coach_id=-1393788898)
    assert tracker_item is not None
    assert tracker_item.workout_id == tracker_workout.id
    assert tracker_item.position == 8


def test_weight_assessment_sync_only_posts_missing_scale_readings(store: Store) -> None:
    existing = AssessmentItem(
        id=1,
        assessment_id=13513325,
        value="90.20",
        attachments=[],
        created_at="2025-02-04T07:00:00.000000Z",
        updated_at="2025-02-04T07:00:00.000000Z",
        date="2025-02-04T07:00:00.000000Z",
        completed_date="2025-02-04",
    )
    history = AssessmentResponse(
        assessment=Assessment(
            id=13513325,
            assessment_group_id=1,
            name="Weight",
            units="kilograms",
            order=1,
            updated_at="2025-02-04T07:00:00.000000Z",
            created_at="2025-02-04T07:00:00.000000Z",
            created_by="client",
            assessment_item_ids=[1],
        ),
        assessment_items=[existing],
    )
    with store.unit_of_work() as tx:
        for index, (timestamp, grams) in enumerate(
            [
                (datetime(2025, 2, 4, 7, tzinfo=UTC), 90200),
                (datetime(2025, 2, 5, 7, tzinfo=UTC), 89950),
                (datetime(2025, 2, 5, 9, tzinfo=UTC), 89700),
            ]
        ):
            tx.add(
                VeSyncWeighIn(
                    source_key=f"source-{index}",
                    measured_at=timestamp,
                    weight_g=grams,
                    is_manual_input=False,
                )
            )

    target = MagicMock()
    target.assessments.get_weights.return_value = history

    def post(request):
        payload = request.assessment_item
        item = AssessmentItem(
            id=len(history.assessment_items) + 1,
            assessment_id=13513325,
            value=payload.value,
            attachments=[],
            created_at=payload.date,
            updated_at=payload.date,
            date=payload.date,
            completed_date=payload.date[:10],
        )
        history.assessment_items.append(item)
        return item

    target.assessments.post.side_effect = post
    syncer = TrackerToTrueCoachSyncronizer(store, target)

    syncer.sync_assessments()
    assert syncer.sync_vesync_weights() == 0
    assert target.assessments.post.call_count == 2
    assert [
        call.args[0].assessment_item.value for call in target.assessments.post.call_args_list
    ] == [
        "89.95",
        "89.70",
    ]
