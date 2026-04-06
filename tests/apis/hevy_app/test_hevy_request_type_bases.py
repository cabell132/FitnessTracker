# Tests Hevy API request type base-class consolidation (issue #9).

from __future__ import annotations

from fitness_tracker.apis.hevy_app.types.common import (
    _BaseRequestExercise,
    _BaseRequestSet,
)
from fitness_tracker.apis.hevy_app.types.routine_post_requests import (
    PostRoutinesRequest,
    PostRoutinesRequestBody,
    PostRoutinesRequestExercise,
    PostRoutinesRequestSet,
)


def test_post_routines_request_set_model_dump_has_core_fields_with_defaults() -> None:
    """Default set row includes all shared measurement and type fields."""
    dumped = PostRoutinesRequestSet().model_dump()
    assert dumped["type"] == "normal"
    assert dumped["weight_kg"] is None
    assert dumped["reps"] is None
    assert dumped["distance_meters"] is None
    assert dumped["duration_seconds"] is None


def test_post_workouts_request_set_isinstance_base_request_set() -> None:
    """Workout POST sets inherit the shared request set base."""
    from fitness_tracker.apis.hevy_app.types.workout_requests import PostWorkoutsRequestSet

    assert isinstance(PostWorkoutsRequestSet(), _BaseRequestSet)


def test_post_routines_request_exercise_isinstance_base_request_exercise() -> None:
    """Routine POST exercises inherit the shared exercise base."""
    row = PostRoutinesRequestExercise(
        exercise_template_id="t1",
        notes="n",
        sets=[PostRoutinesRequestSet()],
    )
    assert isinstance(row, _BaseRequestExercise)


def test_post_routines_request_body_build_matches_manual_construction() -> None:
    """Factory builds the same structure as explicit nested construction."""
    exercises = [
        PostRoutinesRequestExercise(
            exercise_template_id="e1",
            notes="",
            sets=[PostRoutinesRequestSet(reps=5)],
        ),
    ]
    manual = PostRoutinesRequestBody(
        routine=PostRoutinesRequest(
            title="T",
            notes="N",
            exercises=exercises,
            folder_id="f1",
        ),
    )
    built = PostRoutinesRequestBody.build(
        title="T",
        notes="N",
        exercises=exercises,
        folder_id="f1",
    )
    assert built.model_dump() == manual.model_dump()
