"""Tests for operational CLI helpers used by agent commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine

from fitness_tracker import cli
from fitness_tracker.apis.hevy_app.exceptions import HevyAppAPIError
from fitness_tracker.apis.true_coach.types import (
    Meta,
    PutWorkoutItemResponse,
    Workout,
    WorkoutItem,
    WorkoutResponse,
)
from fitness_tracker.database import Store
from fitness_tracker.database.models import Exercise as TrackerExercise
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.true_coach import TrueCoachWorkout


def _truecoach_api_workout() -> Workout:
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


def _truecoach_api_workout_item() -> WorkoutItem:
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


def test_truecoach_due_reads_configured_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    db_url = f"sqlite:///{db_path}"
    store = Store(create_engine(db_url))
    store.init_db()
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=123,
                title="Lower Body",
                due=datetime(2026, 5, 18, tzinfo=UTC),
                state="pending",
                rest_day=False,
            )
        )

    exit_code = cli.main(["truecoach", "due", "--date", "2026-05-18", "--database-url", db_url])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "id | title | due | state | rest_day" in output
    assert "123 | Lower Body | 2026-05-18" in output


def test_truecoach_workouts_due_json_reads_configured_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    db_url = f"sqlite:///{db_path}"
    store = Store(create_engine(db_url))
    store.init_db()
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=123,
                title="Lower Body",
                due=datetime(2026, 5, 18, tzinfo=UTC),
                state="pending",
                rest_day=False,
            )
        )

    exit_code = cli.main(
        [
            "truecoach",
            "workouts",
            "due",
            "--date",
            "2026-05-18",
            "--database-url",
            db_url,
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "ok": True,
        "date": "2026-05-18",
        "workouts": [
            {
                "id": 123,
                "title": "Lower Body",
                "due": "2026-05-18 00:00:00.000000",
                "state": "pending",
                "rest_day": False,
            }
        ],
        "warnings": [],
    }
    assert captured.err == ""


def test_truecoach_workouts_list_json_fetches_remote_workouts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeWorkouts:
        def get(self, **kwargs: Any) -> WorkoutResponse:
            calls.append(kwargs)
            return WorkoutResponse(
                workouts=[_truecoach_api_workout()],
                workout_items=[],
                comments=[],
                meta=Meta(page=1, total_pages=1, per_page=20, total_count=1),
            )

    class FakeClient:
        workouts = FakeWorkouts()

    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: FakeClient())

    exit_code = cli.main(
        ["truecoach", "workouts", "list", "--state", "pending", "--limit", "20", "--json"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [{"order": "asc", "page": 1, "per_page": 20, "states": "pending"}]
    assert json.loads(captured.out) == {
        "ok": True,
        "workouts": [
            {
                "id": 599821297,
                "due": "2026-05-18",
                "title": "Mobility",
                "state": "pending",
                "rest_day": False,
                "program_name": None,
                "workout_item_ids": [-1393788898],
            }
        ],
        "workout_items": [],
        "comments": [],
        "meta": {"page": 1, "per_page": 20, "total_count": 1, "total_pages": 1},
        "warnings": [],
    }
    assert captured.err == ""


def test_truecoach_workouts_inspect_json_fetches_remote_workout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[int] = []

    class FakeWorkouts:
        def inspect(self, workout_id: int) -> WorkoutResponse:
            calls.append(workout_id)
            return WorkoutResponse(
                workouts=[_truecoach_api_workout()],
                workout_items=[_truecoach_api_workout_item()],
                comments=[],
                meta=Meta(page=1, total_pages=1, per_page=1, total_count=1),
            )

    class FakeClient:
        workouts = FakeWorkouts()

    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: FakeClient())

    exit_code = cli.main(
        ["truecoach", "workouts", "inspect", "--workout-id", "599821297", "--json"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [599821297]
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["workout"]["id"] == 599821297
    assert payload["workout"]["title"] == "Mobility"
    assert payload["workout_items"][0]["id"] == -1393788898
    assert payload["warnings"] == []
    assert captured.err == ""


def test_truecoach_workouts_inspect_raw_json_returns_vendor_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[int] = []
    raw_response = {"workouts": [{"id": 599821297, "vendorOnly": True}], "workout_items": []}

    class FakeWorkouts:
        def inspect_raw(self, workout_id: int) -> dict[str, Any]:
            calls.append(workout_id)
            return raw_response

    class FakeClient:
        workouts = FakeWorkouts()

    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: FakeClient())

    exit_code = cli.main(
        [
            "truecoach",
            "workouts",
            "inspect",
            "--workout-id",
            "599821297",
            "--json",
            "--raw",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [599821297]
    assert json.loads(captured.out) == {"ok": True, "raw": raw_response, "warnings": []}
    assert captured.err == ""


def test_truecoach_workout_items_inspect_json_fetches_remote_item(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[int] = []

    class FakeWorkouts:
        def inspect_workout_item(self, item_id: int) -> WorkoutItem:
            calls.append(item_id)
            return _truecoach_api_workout_item()

    class FakeClient:
        workouts = FakeWorkouts()

    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: FakeClient())

    exit_code = cli.main(
        ["truecoach", "workout-items", "inspect", "--item-id", "-1393788898", "--json"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [-1393788898]
    assert json.loads(captured.out) == {
        "ok": True,
        "workout_item": _truecoach_api_workout_item().model_dump(),
        "warnings": [],
    }
    assert captured.err == ""


def test_truecoach_workout_items_inspect_raw_json_returns_vendor_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[int] = []
    raw_response = {"workout_item": {"id": -1393788898, "vendorOnly": True}}

    class FakeWorkouts:
        def inspect_workout_item_raw(self, item_id: int) -> dict[str, Any]:
            calls.append(item_id)
            return raw_response

    class FakeClient:
        workouts = FakeWorkouts()

    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: FakeClient())

    exit_code = cli.main(
        [
            "truecoach",
            "workout-items",
            "inspect",
            "--item-id",
            "-1393788898",
            "--json",
            "--raw",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [-1393788898]
    assert json.loads(captured.out) == {"ok": True, "raw": raw_response, "warnings": []}
    assert captured.err == ""


def test_truecoach_workout_items_update_result_dry_run_validates_request_without_mutating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "truecoach-update-request.json"
    request_path.write_text(
        json.dumps(
            {
                "workout_item": {
                    **_truecoach_api_workout_item().model_dump(),
                    "state": "completed",
                    "state_event": "mark_as_completed",
                    "result": "8 x 80 kg\n7 x 80 kg",
                }
            }
        ),
        encoding="utf-8",
    )

    class FakeWorkouts:
        def update_workout_item(self, item_id: int, workout_item: Any) -> None:
            msg = "dry-run must not mutate True Coach"
            raise AssertionError(msg)

    class FakeClient:
        workouts = FakeWorkouts()

    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: FakeClient())

    exit_code = cli.main(
        [
            "truecoach",
            "workout-items",
            "update-result",
            "--request",
            str(request_path),
            "--dry-run",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "ok": True,
        "action": "dry_run",
        "workout_item_id": -1393788898,
        "workout_id": 599821297,
        "result": "8 x 80 kg\n7 x 80 kg",
        "response_path": None,
        "warnings": [],
    }
    assert captured.err == ""


def test_truecoach_workout_items_update_result_json_reports_invalid_request(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "bad-request.json"
    request_path.write_text(json.dumps({"workout_item": {"id": -1393788898}}), encoding="utf-8")

    exit_code = cli.main(
        [
            "truecoach",
            "workout-items",
            "update-result",
            "--request",
            str(request_path),
            "--dry-run",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.out)["ok"] is False
    assert "workout_id" in json.loads(captured.out)["error"]
    assert captured.err == ""


def test_truecoach_workout_items_update_result_json_requires_confirmation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "truecoach-update-request.json"
    request_path.write_text(
        json.dumps({"workout_item": _truecoach_api_workout_item().model_dump()}),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            "truecoach",
            "workout-items",
            "update-result",
            "--request",
            str(request_path),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.out) == {
        "ok": False,
        "error": "real apply requires --yes; use --dry-run to validate only",
    }
    assert captured.err == ""


def test_truecoach_workout_items_update_result_applies_and_writes_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[int, Any]] = []
    request_path = tmp_path / "truecoach-update-request.json"
    response_path = tmp_path / "truecoach-response.json"
    update_payload = {
        **_truecoach_api_workout_item().model_dump(),
        "state": "completed",
        "state_event": "mark_as_completed",
        "result": "8 x 80 kg",
    }
    request_path.write_text(json.dumps({"workout_item": update_payload}), encoding="utf-8")
    response_item = _truecoach_api_workout_item().model_copy(
        update={"state": "completed", "result": "8 x 80 kg"}
    )

    class FakeWorkouts:
        def update_workout_item(self, item_id: int, workout_item: Any) -> PutWorkoutItemResponse:
            calls.append((item_id, workout_item))
            return PutWorkoutItemResponse(workout_item=response_item)

    class FakeClient:
        workouts = FakeWorkouts()

    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: FakeClient())

    exit_code = cli.main(
        [
            "truecoach",
            "workout-items",
            "update-result",
            "--request",
            str(request_path),
            "--yes",
            "--response-path",
            str(response_path),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls[0][0] == -1393788898
    assert calls[0][1].result == "8 x 80 kg"
    assert calls[0][1].state_event == "mark_as_completed"
    response_payload = {"workout_item": response_item.model_dump()}
    assert json.loads(response_path.read_text(encoding="utf-8")) == response_payload
    assert json.loads(captured.out) == {
        "ok": True,
        "action": "updated",
        "workout_item_id": -1393788898,
        "workout_id": 599821297,
        "result": "8 x 80 kg",
        "response_path": str(response_path),
        "response": response_payload,
        "warnings": [],
    }
    assert captured.err == ""


def test_truecoach_workout_items_update_result_text_file_builds_request_from_remote_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result_path = tmp_path / "result.txt"
    result_path.write_text("8 x 80 kg\n", encoding="utf-8")
    calls: list[int] = []

    class FakeWorkouts:
        def inspect_workout_item(self, item_id: int) -> WorkoutItem:
            calls.append(item_id)
            return _truecoach_api_workout_item()

    class FakeClient:
        workouts = FakeWorkouts()

    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: FakeClient())

    exit_code = cli.main(
        [
            "truecoach",
            "workout-items",
            "update-result",
            "--item-id",
            "-1393788898",
            "--text-file",
            str(result_path),
            "--dry-run",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [-1393788898]
    assert json.loads(captured.out)["result"] == "8 x 80 kg"
    assert captured.err == ""


def test_truecoach_workouts_import_recent_json_preserves_import_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    db_url = f"sqlite:///{db_path}"
    Store(create_engine(db_url)).init_db()
    calls: list[dict[str, Any]] = []

    class FakeWorkouts:
        def get(self, **kwargs: Any) -> WorkoutResponse:
            calls.append(kwargs)
            return WorkoutResponse(
                workouts=[_truecoach_api_workout()],
                workout_items=[_truecoach_api_workout_item()],
                comments=[],
                meta=Meta(page=1, total_pages=1, per_page=20, total_count=1),
            )

    class FakeClient:
        workouts = FakeWorkouts()

    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: FakeClient())

    exit_code = cli.main(
        [
            "truecoach",
            "workouts",
            "import-recent",
            "--pages",
            "2",
            "--database-url",
            db_url,
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [
        {
            "order": "desc",
            "page": 1,
            "per_page": 20,
            "states": ["pending", "completed", "missed"],
        }
    ]
    assert json.loads(captured.out) == {
        "ok": True,
        "imported_pages": 1,
        "imported_workouts": 1,
        "imported_items": 1,
        "warnings": [],
    }
    assert captured.err == ""


def test_truecoach_import_recent_legacy_command_remains_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    db_url = f"sqlite:///{db_path}"
    Store(create_engine(db_url)).init_db()
    calls: list[dict[str, Any]] = []

    class FakeWorkouts:
        def get(self, **kwargs: Any) -> WorkoutResponse:
            calls.append(kwargs)
            return WorkoutResponse(
                workouts=[_truecoach_api_workout()],
                workout_items=[],
                comments=[],
                meta=Meta(page=1, total_pages=1, per_page=20, total_count=1),
            )

    class FakeClient:
        workouts = FakeWorkouts()

    monkeypatch.setattr(cli, "_truecoach_client_from_config", lambda: FakeClient())

    exit_code = cli.main(
        ["truecoach", "import-recent", "--pages", "1", "--database-url", db_url, "--json"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [
        {
            "order": "desc",
            "page": 1,
            "per_page": 20,
            "states": ["pending", "completed", "missed"],
        }
    ]
    assert json.loads(captured.out)["imported_workouts"] == 1
    assert captured.err == ""


def test_hevy_routines_inspect_prints_compact_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_hevy_api_json",
        lambda *args, **kwargs: {
            "routine": {
                "id": "routine-1",
                "title": "18 May 2026\nLower Body\n123",
                "exercises": [
                    {
                        "exercise_template_id": "template-a",
                        "superset_id": 0,
                        "notes": "A1",
                        "sets": [{"type": "normal", "reps": 5}],
                    },
                    {
                        "exercise_template_id": "template-b",
                        "superset_id": 0,
                        "notes": "A2",
                        "sets": [],
                    },
                ],
            }
        },
    )

    exit_code = cli.main(["hevy", "routines", "inspect", "routine-1"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "exercises: 2" in output
    assert "superset_ids: [0, 0]" in output
    assert "empty_set_blocks: [2]" in output


def test_hevy_routines_inspect_json_keeps_stdout_parseable_and_warnings_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_hevy_api_json",
        lambda *args, **kwargs: {
            "routine": {
                "id": "routine-1",
                "title": "18 May 2026\nLower Body\n123",
                "exercises": [
                    {
                        "exercise_template_id": "template-a",
                        "superset_id": 0,
                        "notes": "A1",
                        "sets": [{"type": "normal", "reps": 5}],
                    },
                    {
                        "exercise_template_id": "template-b",
                        "superset_id": 0,
                        "notes": "A2",
                        "sets": [],
                    },
                ],
            }
        },
    )

    exit_code = cli.main(["hevy", "routines", "inspect", "routine-1", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "ok": True,
        "routine": {
            "id": "routine-1",
            "title": "18 May 2026\nLower Body\n123",
            "exercise_count": 2,
            "superset_ids": [0, 0],
            "empty_set_blocks": [2],
            "exercises": [
                {
                    "position": 1,
                    "superset_id": 0,
                    "exercise_template_id": "template-a",
                    "notes": "A1",
                    "set_count": 1,
                },
                {
                    "position": 2,
                    "superset_id": 0,
                    "exercise_template_id": "template-b",
                    "notes": "A2",
                    "set_count": 0,
                },
            ],
        },
        "warnings": ["Routine has empty set blocks: [2]"],
    }
    assert captured.err == "Warning: Routine has empty set blocks: [2]\n"


def test_hevy_workouts_inspect_prints_compact_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_hevy_api_json",
        lambda *args, **kwargs: {
            "workout": {
                "id": "workout-1",
                "title": "2024-04-10 Upper",
                "start_time": "2024-04-10T06:43:00Z",
                "end_time": "2024-04-10T08:30:00Z",
                "exercises": [
                    {
                        "exercise_template_id": "template-a",
                        "superset_id": 0,
                        "name": "Row",
                        "notes": "",
                        "sets": [{"type": "normal", "distance_meters": 500}],
                    },
                    {
                        "exercise_template_id": "template-b",
                        "superset_id": None,
                        "name": "Down Regulate",
                        "notes": None,
                        "sets": [],
                    },
                ],
            }
        },
    )

    exit_code = cli.main(["hevy", "workouts", "inspect", "workout-1"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "start_time: 2024-04-10T06:43:00Z" in output
    assert "exercises: 2" in output
    assert "superset_ids: [0, None]" in output
    assert "empty_set_blocks: [2]" in output


def test_hevy_routines_create_from_json_validates_and_writes_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_hevy_api_json(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"args": args, "kwargs": kwargs})
        return {"routine": [{"id": "routine-2"}]}

    request_path = tmp_path / "hevy-request.manual.json"
    response_path = tmp_path / "response.json"
    request_path.write_text(
        json.dumps(
            {
                "routine": {
                    "title": "18 May 2026\nLower Body\n123",
                    "folder_id": None,
                    "notes": "",
                    "exercises": [
                        {
                            "exercise_template_id": "template-a",
                            "superset_id": 0,
                            "notes": "A1",
                            "rest_seconds": 0,
                            "sets": [
                                {
                                    "type": "normal",
                                    "weight_kg": None,
                                    "reps": 5,
                                    "distance_meters": None,
                                    "duration_seconds": None,
                                }
                            ],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_hevy_api_json", fake_hevy_api_json)

    exit_code = cli.main(
        [
            "hevy",
            "routines",
            "create-from-json",
            str(request_path),
            "--response-path",
            str(response_path),
        ]
    )

    assert exit_code == 0
    assert calls[0]["args"] == ("POST", "/routines")
    assert json.loads(response_path.read_text(encoding="utf-8")) == {
        "routine": [{"id": "routine-2"}]
    }
    assert "Created Hevy routine: routine-2" in capsys.readouterr().out


def test_hevy_routines_create_from_json_json_skips_response_artifact_without_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "hevy-request.manual.json"
    request_path.write_text(
        json.dumps(
            {
                "routine": {
                    "title": "18 May 2026\nLower Body\n123",
                    "notes": "",
                    "exercises": [
                        {
                            "exercise_template_id": "template-a",
                            "notes": "A1",
                            "sets": [{"type": "normal", "reps": 5}],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli,
        "_hevy_api_json",
        lambda *args, **kwargs: {"routine": {"id": "routine-2"}},
    )

    exit_code = cli.main(["hevy", "routines", "create-from-json", str(request_path), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {
        "ok": True,
        "action": "created",
        "routine_id": "routine-2",
        "response_path": None,
        "response": {"routine": {"id": "routine-2"}},
        "warnings": [],
    }
    assert captured.err == ""
    assert not (tmp_path / "hevy-request.manual.response.json").exists()


def test_hevy_routines_inspect_json_reports_nonzero_errors_as_json_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_hevy_api_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            HevyAppAPIError("upstream failed", url="https://api.hevyapp.com/v1/routines/404")
        ),
    )

    exit_code = cli.main(["hevy", "routines", "inspect", "routine-404", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.out) == {"ok": False, "error": "upstream failed"}
    assert captured.err == ""


def test_hevy_routines_update_from_json_strips_folder_and_nulls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_hevy_api_json(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"args": args, "kwargs": kwargs})
        return {"routine": {"id": "routine-3"}}

    request_path = tmp_path / "hevy-request.json"
    request_path.write_text(
        json.dumps(
            {
                "routine": {
                    "title": "Routine",
                    "folder_id": "folder-1",
                    "notes": "",
                    "exercises": [
                        {
                            "exercise_template_id": "row",
                            "notes": "5 x 400m",
                            "sets": [{"type": "normal", "distance_meters": 400}],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_hevy_api_json", fake_hevy_api_json)

    exit_code = cli.main(["hevy", "routines", "update-from-json", "routine-3", str(request_path)])

    assert exit_code == 0
    assert calls[0]["args"] == ("PUT", "/routines/routine-3")
    sent = calls[0]["kwargs"]["json_body"]
    assert sent["routine"]["notes"] == "Updated from JSON."
    assert "folder_id" not in sent["routine"]
    assert "rep_range" not in sent["routine"]["exercises"][0]["sets"][0]
    assert "Updated Hevy routine: routine-3" in capsys.readouterr().out


def test_hevy_routines_diff_json_reports_normalized_differences(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "hevy-request.json"
    request_path.write_text(
        json.dumps(
            {
                "routine": {
                    "title": "Routine",
                    "notes": "",
                    "exercises": [
                        {
                            "exercise_template_id": "row",
                            "notes": "5 x 400m",
                            "sets": [{"type": "normal", "distance_meters": 400}],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli,
        "_hevy_api_json",
        lambda *args, **kwargs: {
            "routine": {
                "id": "routine-3",
                "title": "Routine",
                "exercises": [
                    {
                        "exercise_template_id": "row",
                        "title": "Rowing Machine",
                        "notes": "5 x 400m",
                        "sets": [
                            {
                                "index": 0,
                                "type": "normal",
                                "distance_meters": 400,
                                "duration_seconds": 99,
                            }
                        ],
                    }
                ],
            }
        },
    )

    exit_code = cli.main(
        [
            "hevy",
            "routines",
            "diff-json",
            "routine-3",
            str(request_path),
            "--include-low-signal",
        ]
    )

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "# Hevy Routine Diff: routine-3" in output
    assert "## 1. Rowing Machine (low_signal_sets)" in output
    assert '"duration_seconds": 99' in output


def test_hevy_routines_diff_json_hides_low_signal_differences_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "hevy-request.json"
    request_path.write_text(
        json.dumps(
            {
                "routine": {
                    "title": "Routine",
                    "notes": "",
                    "exercises": [
                        {
                            "exercise_template_id": "row",
                            "sets": [{"type": "normal", "distance_meters": 400}],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli,
        "_hevy_api_json",
        lambda *args, **kwargs: {
            "routine": {
                "id": "routine-3",
                "title": "Routine",
                "exercises": [
                    {
                        "exercise_template_id": "row",
                        "title": "Rowing Machine",
                        "sets": [
                            {
                                "type": "normal",
                                "distance_meters": 400,
                                "duration_seconds": 99,
                            }
                        ],
                    }
                ],
            }
        },
    )

    exit_code = cli.main(["hevy", "routines", "diff-json", "routine-3", str(request_path)])

    assert exit_code == 0
    assert "No normalized differences found." in capsys.readouterr().out


def test_hevy_exercise_templates_fuzzy_find_prints_ranked_matches(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_hevy_api_pages",
        lambda *args, **kwargs: [
            {
                "id": "old",
                "title": "Cuban Press (Dumbbell)",
                "type": "weight_reps",
                "equipment": "dumbbell",
                "primary_muscle_group": "shoulders",
            },
            {
                "id": "other",
                "title": "Lat Pulldown",
                "type": "weight_reps",
                "equipment": "machine",
                "primary_muscle_group": "lats",
            },
        ],
    )

    exit_code = cli.main(
        [
            "hevy",
            "exercise-templates",
            "fuzzy-find",
            "--title",
            "Dumbbell Cuban Press",
            "--limit",
            "1",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "old | Cuban Press (Dumbbell)" in output


def test_hevy_exercise_templates_find_prints_exact_matches(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_find_remote_hevy_templates",
        lambda title: [
            {
                "id": "template-1",
                "title": title,
                "type": "weight_reps",
                "equipment": "dumbbell",
                "primary_muscle_group": "shoulders",
            }
        ],
    )

    exit_code = cli.main(["hevy", "exercise-templates", "find", "--title", "Dumbbell Cuban Press"])

    assert exit_code == 0
    assert (
        "template-1 | Dumbbell Cuban Press | weight_reps | dumbbell | shoulders"
        in capsys.readouterr().out
    )


def test_hevy_exercise_templates_create_dry_run_reports_template(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    db_url = f"sqlite:///{db_path}"
    Store(create_engine(db_url)).init_db()

    exit_code = cli.main(
        [
            "hevy",
            "exercise-templates",
            "create",
            "--title",
            "Dumbbell Cuban Press",
            "--type",
            "weight_reps",
            "--equipment",
            "dumbbell",
            "--muscle-group",
            "shoulders",
            "--database-url",
            db_url,
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert "Would create Hevy template: Dumbbell Cuban Press" in capsys.readouterr().out


def test_hevy_templates_namespace_is_not_available(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as help_exit:
        cli.main(["--help"])

    assert help_exit.value.code == 0
    assert "hevy-templates" not in capsys.readouterr().out

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["hevy-templates", "fuzzy-find", "--title", "Dumbbell Cuban Press"])

    assert exc_info.value.code == 2


def test_hevy_routine_folders_ensure_reuses_existing_folder(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_hevy_api_pages",
        lambda *args, **kwargs: [{"id": 10, "title": "True Coach"}],
    )

    exit_code = cli.main(["hevy", "routine-folders", "ensure", "--title", "True Coach"])

    assert exit_code == 0
    assert "10 | True Coach" in capsys.readouterr().out


def test_exercise_links_set_updates_join_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    db_url = f"sqlite:///{db_path}"
    store = Store(create_engine(db_url))
    store.init_db()
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppExercise(
                id="hevy-row",
                name="Rowing Machine",
                type="distance_duration",
                equipment="machine",
            )
        )
        uow.session.add(TrackerExercise(name="Row", true_coach_id=123))

    class DummyConfig:
        email = "test@example.com"
        hevy_api_key = type("Secret", (), {"get_secret_value": lambda self: "key"})()
        hevy_web_api_key = type("Secret", (), {"get_secret_value": lambda self: "web"})()

    monkeypatch.setattr(cli.Config, "from_env", lambda: DummyConfig())

    exit_code = cli.main(
        [
            "exercise-links",
            "set",
            "--truecoach-exercise-id",
            "123",
            "--hevy-template-id",
            "hevy-row",
            "--database-url",
            db_url,
        ]
    )

    assert exit_code == 0
    with store.unit_of_work() as uow:
        row = uow.session.query(TrackerExercise).filter_by(true_coach_id=123).one()
        assert row.hevy_app_id == "hevy-row"
    assert "Linked TrueCoach exercise 123 to Hevy template hevy-row" in capsys.readouterr().out
