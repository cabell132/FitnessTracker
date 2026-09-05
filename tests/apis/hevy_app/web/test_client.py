"""Website API contracts tested through the client interface."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.hevy_app.web import HevyWebClient


class Session:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def make_request(self, **kwargs):
        self.calls.append(kwargs)
        response = next(self.responses, None)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def workout():
    return {
        "id": "workout-1",
        "name": "Pull",
        "start_time": 1788411600,
        "end_time": 1788415200,
        "routine_id": "routine-1",
        "biometrics": {"heart_rate_samples": []},
        "future_workout_field": {"retained": True},
        "exercises": [
            {
                "id": "exercise-occurrence-1",
                "exercise_template_id": "template-1",
                "title": "Row",
                "rest_seconds": 90,
                "future_exercise_field": "retained",
                "sets": [
                    {
                        "id": "set-1",
                        "index": 0,
                        "indicator": "normal",
                        "completed_at": "2026-09-03T05:44:00.560Z",
                        "weight_kg": 30,
                        "reps": 10,
                        "prs": ["weight"],
                        "future_set_field": {"retained": True},
                    }
                ],
            }
        ],
        "request_url": "https://api.hevyapp.com/workout/workout-1",
    }


def test_workout_preserves_timing_identity_and_unknown_fields(workout):
    session = Session(workout)
    result = HevyWebClient(session).workouts.get("workout-1")
    exercise = result.exercises[0]
    assert result.name == "Pull"
    assert result.start_time == 1788411600
    assert exercise.rest_seconds == 90
    assert exercise.id == "exercise-occurrence-1"
    assert exercise.sets[0].id == "set-1"
    assert exercise.sets[0].completed_at == datetime(2026, 9, 3, 5, 44, 0, 560000, UTC)
    dumped = result.model_dump(mode="json")
    assert dumped["future_workout_field"] == {"retained": True}
    assert dumped["exercises"][0]["future_exercise_field"] == "retained"
    assert dumped["exercises"][0]["sets"][0]["future_set_field"] == {"retained": True}
    assert "request_url" not in dumped
    assert session.calls == [{"method": "GET", "endpoint": "/workout/workout-1", "params": {}}]


@pytest.mark.parametrize("timestamp", [None, "missing"])
def test_old_sets_keep_missing_completion_time(workout, timestamp):
    record = workout["exercises"][0]["sets"][0]
    if timestamp == "missing":
        del record["completed_at"]
    else:
        record["completed_at"] = timestamp
    result = HevyWebClient(Session(workout)).workouts.get("workout-1")
    assert result.exercises[0].sets[0].completed_at is None


def test_malformed_timestamp_is_not_silently_dropped(workout):
    workout["exercises"][0]["sets"][0]["completed_at"] = "2026-09-03T05:44:00"
    with pytest.raises(ValidationError):
        HevyWebClient(Session(workout)).workouts.get("workout-1")


def test_pagination_continues_short_pages_and_deduplicates_overlap(workout):
    other = deepcopy(workout)
    other["id"] = "workout-2"
    session = Session(
        {"workouts": [workout]},
        {"workouts": [workout, other]},
        {"workouts": []},
    )
    result = list(HevyWebClient(session).workouts.iter_all("athlete", page_size=20))
    assert [item.id for item in result] == ["workout-1", "workout-2"]
    assert [call["params"]["offset"] for call in session.calls] == [0, 1, 3]
    assert all(call["params"]["username"] == "athlete" for call in session.calls)


def test_pagination_fails_on_repeated_page(workout):
    client = HevyWebClient(Session({"workouts": [workout]}, {"workouts": [workout]}))
    with pytest.raises(HevyAppAPIError, match="no progress"):
        list(client.workouts.iter_all("athlete"))


@pytest.mark.parametrize("response", [None, {}, {"workouts": None}, {"workouts": "invalid"}])
def test_bad_page_is_not_treated_as_end_of_history(response):
    with pytest.raises((HevyAppAPIError, ValidationError)):
        list(HevyWebClient(Session(response)).workouts.iter_all("athlete"))


def test_batch_uses_workout_index_and_session_list_envelope(workout):
    session = Session({"results": [workout], "request_url": "unused"})
    result = HevyWebClient(session).workouts.batch(123)
    assert result[0].exercises[0].sets[0].completed_at is not None
    assert session.calls[0]["endpoint"] == "/workouts_batch/123"


def test_routine_sets_do_not_require_performed_set_fields():
    response = {
        "routine": {
            "id": "routine-1",
            "title": "Pull",
            "folder_id": 2,
            "exercises": [
                {
                    "title": "Row",
                    "rest_seconds": 90,
                    "sets": [
                        {"index": 0, "indicator": "normal", "rep_range": {"start": 8, "end": 12}}
                    ],
                }
            ],
        }
    }
    result = HevyWebClient(Session(response)).routines.get("routine-1")
    assert result.model_dump()["exercises"][0]["sets"][0]["rep_range"] == {"start": 8, "end": 12}


def test_custom_template_metadata_and_empty_lists():
    client = HevyWebClient(
        Session(
            {
                "results": [
                    {
                        "id": "template-1",
                        "title": "Row",
                        "exercise_type": "weight_reps",
                        "is_custom": True,
                        "is_archived": True,
                        "priority": 12,
                    }
                ]
            },
            {"results": []},
        )
    )
    template = client.exercises.list_custom()[0]
    assert template.is_archived
    assert template.model_dump()["priority"] == 12
    assert client.exercises.units() == []


def test_mutations_use_distinct_website_envelopes_and_sync_flag():
    session = Session()
    client = HevyWebClient(session)
    routine = {"title": "Pull", "exercises": []}
    client.routines.update("routine-1", routine)
    client.routines.delete("routine-1")
    client.folders.update({"id": 2, "title": "Block"})
    client.folders.reorder([{"id": 2, "index": 0}])
    assert session.calls == [
        {
            "method": "PUT",
            "endpoint": "/routine/routine-1",
            "json": {"routine": routine},
            "params": {"sendSyncEventToMobileApp": "true"},
        },
        {
            "method": "DELETE",
            "endpoint": "/routine/routine-1",
            "params": {"sendSyncEventToMobileApp": "true"},
        },
        {
            "method": "PUT",
            "endpoint": "/routine_folder",
            "json": {"id": 2, "title": "Block"},
            "params": {"sendSyncEventToMobileApp": "true"},
        },
        {
            "method": "PUT",
            "endpoint": "/routine_folder_order",
            "json": {"reorders": [{"id": 2, "index": 0}]},
            "params": {"sendSyncEventToMobileApp": "true"},
        },
    ]


def test_custom_exercise_update_uses_body_id_and_rejects_missing_id():
    session = Session()
    client = HevyWebClient(session)
    exercise = {"id": "template-1", "title": "Row"}
    client.exercises.update(exercise)
    with pytest.raises(TypeError, match="id"):
        client.exercises.update({"title": "Row"})
    assert session.calls == [
        {
            "method": "PUT",
            "endpoint": "/custom_exercise_template/template-1",
            "json": {"exercise": exercise},
        }
    ]


def test_webhook_404_propagates_and_subscription_is_explicit():
    error = HevyAppAPIError("Not found", url="/webhook-subscription", status_code=404)
    session = Session(error, None)
    client = HevyWebClient(session)
    with pytest.raises(HevyAppAPIError) as caught:
        client.webhooks.get()
    assert caught.value is error
    token = "test-token"
    client.webhooks.subscribe("https://example.com/hevy", auth_token=token)
    assert session.calls[-1] == {
        "method": "POST",
        "endpoint": "/webhook-subscription",
        "json": {"url": "https://example.com/hevy", "authToken": "test-token"},
    }


def test_path_values_are_encoded_and_invalid_paging_makes_no_request():
    session = Session({"results": []})
    client = HevyWebClient(session)
    assert client.workouts.comments("id/with?reserved") == []
    assert session.calls[0]["endpoint"] == "/workout_comments/id%2Fwith%3Freserved"
    with pytest.raises(ValueError, match="positive limit"):
        client.workouts.list("athlete", limit=0)
    assert len(session.calls) == 1
