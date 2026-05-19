"""Tests for operational CLI helpers used by agent commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine

from fitness_tracker import cli
from fitness_tracker.database import Store
from fitness_tracker.database.models import Exercise as TrackerExercise
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.true_coach import TrueCoachWorkout


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


def test_hevy_templates_fuzzy_find_prints_ranked_matches(
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
            "hevy-templates",
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
