from __future__ import annotations

from typing import Any

from fitness_tracker.apis.true_coach.workouts import TrueCoachWorkouts


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def make_request(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "workouts": [_workout_payload()],
            "workout_items": [],
            "comments": [],
            "meta": {"page": 1, "total_pages": 1, "per_page": 1, "total_count": 1},
        }


def test_inspect_fetches_single_workout_endpoint() -> None:
    session = FakeSession()
    client = TrueCoachWorkouts(session=session)

    response = client.inspect(599821297)

    assert session.calls == [{"method": "GET", "endpoint": "clients/2876143/workouts/599821297"}]
    assert response is not None
    assert response.workouts[0].id == 599821297


def test_inspect_raw_returns_vendor_payload() -> None:
    session = FakeSession()
    client = TrueCoachWorkouts(session=session)

    response = client.inspect_raw(599821297)

    assert response == {
        "workouts": [_workout_payload()],
        "workout_items": [],
        "comments": [],
        "meta": {"page": 1, "total_pages": 1, "per_page": 1, "total_count": 1},
    }


def _workout_payload() -> dict[str, Any]:
    return {
        "id": 599821297,
        "due": "2026-05-18",
        "short_description": "",
        "created_at": "2026-05-18T00:00:00.000000Z",
        "updated_at": "2026-05-18T00:10:00.000000Z",
        "title": "Mobility",
        "state": "pending",
        "rest_day": False,
        "rest_day_instructions": "",
        "warmup": None,
        "warmup_selected_exercises": [],
        "cooldown_selected_exercises": [],
        "cooldown": None,
        "position": None,
        "order": 1,
        "uuid": "uuid-599821297",
        "program_name": None,
        "hidden": False,
        "edit_client_workout": True,
        "client_id": 2876143,
        "comment_ids": [],
        "note_id": None,
        "program_id": None,
        "workout_item_ids": [],
    }
