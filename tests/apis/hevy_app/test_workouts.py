from __future__ import annotations

from fitness_tracker.apis.hevy_app.workouts import HevyAppWorkouts
from fitness_tracker.apis.hevy_app.types import Exercise, Set, Workout


class FakeSession:
    def __init__(self) -> None:
        self.calls = []

    def make_request(self, **kwargs):
        self.calls.append(kwargs)
        return {"workout": [_workout_payload("w1")]}


def test_update_workout_wraps_payload_for_hevy_api() -> None:
    session = FakeSession()
    client = HevyAppWorkouts(session=session)
    workout = Workout(**_workout_payload("w1"))

    client.update_workout("w1", workout)

    assert session.calls[0]["method"] == "PUT"
    assert session.calls[0]["endpoint"] == "/workouts/w1"
    assert "workout" in session.calls[0]["json"]
    assert "id" not in session.calls[0]["json"]["workout"]
    assert "updated_at" not in session.calls[0]["json"]["workout"]
    assert session.calls[0]["json"]["workout"]["is_private"] is False
    assert session.calls[0]["json"]["workout"]["description"] is None
    exercise = session.calls[0]["json"]["workout"]["exercises"][0]
    assert "index" not in exercise
    assert "title" not in exercise
    assert exercise["notes"] is None
    assert "index" not in exercise["sets"][0]


def test_update_workout_accepts_wrapped_list_response() -> None:
    session = FakeSession()
    client = HevyAppWorkouts(session=session)
    workout = Workout(**_workout_payload("w1"))

    updated = client.update_workout("w1", workout)

    assert updated is not None
    assert updated.id == "w1"


def _workout_payload(workout_id: str) -> dict:
    return {
        "id": workout_id,
        "title": "Workout",
        "description": "",
        "start_time": "2026-01-01T00:00:00Z",
        "end_time": "2026-01-01T01:00:00Z",
        "updated_at": "2026-01-01T01:00:00Z",
        "created_at": "2026-01-01T00:00:00Z",
        "exercises": [
            Exercise(
                index=0,
                title="Exercise",
                notes="",
                exercise_template_id="template",
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
            ).model_dump()
        ],
    }
