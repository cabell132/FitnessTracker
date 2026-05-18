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
