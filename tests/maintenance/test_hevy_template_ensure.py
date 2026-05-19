from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from fitness_tracker import cli
from fitness_tracker.apis.hevy_app.types import CreateCustomExerciseRequestBody
from fitness_tracker.database import Store
from fitness_tracker.database.models.hevy_app import HevyAppExercise


class FakeHevyExercises:
    def __init__(self, created_id: int = 9001) -> None:
        self.created_id = created_id
        self.created: list[CreateCustomExerciseRequestBody] = []

    def create(self, exercise: CreateCustomExerciseRequestBody):
        self.created.append(exercise)
        return type("CreatedTemplate", (), {"id": self.created_id})()


class FakeHevyClient:
    def __init__(self) -> None:
        self.exercises = FakeHevyExercises()


def test_ensure_from_plan_dry_run_reports_missing_templates_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = _write_plan(tmp_path, [_missing_template("Single-Leg Isometric Calf Raise")])
    store, db_url = _store(tmp_path)
    fake_client = FakeHevyClient()
    monkeypatch.setattr(cli, "_hevy_client_from_config", lambda: fake_client)

    exit_code = cli.main(
        [
            "hevy",
            "exercise-templates",
            "ensure-from-plan",
            str(plan_path),
            "--database-url",
            db_url,
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert "Would create Hevy template: Single-Leg Isometric Calf Raise" in capsys.readouterr().out
    assert fake_client.exercises.created == []
    with store.unit_of_work() as uow:
        assert uow.session.get_all(HevyAppExercise) == []


def test_ensure_from_plan_json_reports_missing_templates_without_prose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = _write_plan(tmp_path, [_missing_template("Single-Leg Isometric Calf Raise")])
    store, db_url = _store(tmp_path)
    fake_client = FakeHevyClient()
    monkeypatch.setattr(cli, "_hevy_client_from_config", lambda: fake_client)

    exit_code = cli.main(
        [
            "hevy",
            "exercise-templates",
            "ensure-from-plan",
            str(plan_path),
            "--database-url",
            db_url,
            "--dry-run",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["would_create"] == [
        {
            "title": "Single-Leg Isometric Calf Raise",
            "expected_type": "duration",
            "equipment_category": "bodyweight",
            "muscle_group": "calves",
            "other_muscles": [],
            "status": "missing",
            "source_workout_item_ids": [1003],
            "matching_template_ids": [],
        }
    ]
    assert captured.err == ""
    assert fake_client.exercises.created == []
    with store.unit_of_work() as uow:
        assert uow.session.get_all(HevyAppExercise) == []


def test_ensure_from_plan_yes_creates_and_persists_missing_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = _write_plan(tmp_path, [_missing_template("Single-Leg Isometric Calf Raise")])
    store, db_url = _store(tmp_path)
    fake_client = FakeHevyClient()
    monkeypatch.setattr(cli, "_hevy_client_from_config", lambda: fake_client)

    exit_code = cli.main(
        [
            "hevy",
            "exercise-templates",
            "ensure-from-plan",
            str(plan_path),
            "--database-url",
            db_url,
            "--yes",
        ]
    )

    assert exit_code == 0
    assert "Created Hevy template: Single-Leg Isometric Calf Raise" in capsys.readouterr().out
    assert [created.exercise.title for created in fake_client.exercises.created] == [
        "Single-Leg Isometric Calf Raise"
    ]
    with store.unit_of_work() as uow:
        exercise = uow.session.get(HevyAppExercise, id="9001")
        assert exercise is not None
        assert exercise.name == "Single-Leg Isometric Calf Raise"
        assert exercise.type == "duration"
        assert exercise.equipment == "bodyweight"
        assert exercise.default is False


def test_ensure_from_plan_skips_existing_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = _write_plan(tmp_path, [_existing_template("Isometric Seated Knee Extension")])
    store, db_url = _store(tmp_path)
    fake_client = FakeHevyClient()
    monkeypatch.setattr(cli, "_hevy_client_from_config", lambda: fake_client)

    exit_code = cli.main(
        [
            "hevy",
            "exercise-templates",
            "ensure-from-plan",
            str(plan_path),
            "--database-url",
            db_url,
            "--yes",
        ]
    )

    assert exit_code == 0
    assert "Already exists: Isometric Seated Knee Extension" in capsys.readouterr().out
    assert fake_client.exercises.created == []
    with store.unit_of_work() as uow:
        assert uow.session.get_all(HevyAppExercise) == []


def test_ensure_from_plan_refuses_ambiguous_templates_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = _write_plan(tmp_path, [_ambiguous_template("Isometric Seated Knee Extension")])
    store, db_url = _store(tmp_path)
    fake_client = FakeHevyClient()
    monkeypatch.setattr(cli, "_hevy_client_from_config", lambda: fake_client)

    exit_code = cli.main(
        [
            "hevy",
            "exercise-templates",
            "ensure-from-plan",
            str(plan_path),
            "--database-url",
            db_url,
            "--yes",
        ]
    )

    assert exit_code == 2
    assert (
        "Ambiguous required Hevy template(s): Isometric Seated Knee Extension (hevy-a, hevy-b)"
        in (capsys.readouterr().out)
    )
    assert fake_client.exercises.created == []
    with store.unit_of_work() as uow:
        assert uow.session.get_all(HevyAppExercise) == []


def _store(tmp_path: Path) -> tuple[Store, str]:
    db_path = tmp_path / "tracker.sqlite"
    db_url = f"sqlite:///{db_path}"
    store = Store(create_engine(db_url))
    store.init_db()
    return store, db_url


def _write_plan(tmp_path: Path, required_templates: list[dict]) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "source_id": 1003,
                        "required_hevy_templates": required_templates,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _missing_template(title: str) -> dict:
    return {
        "title": title,
        "expected_type": "duration",
        "equipment_category": "bodyweight",
        "muscle_group": "calves",
        "other_muscles": [],
        "status": "missing",
        "source_workout_item_ids": [1003],
        "matching_template_ids": [],
    }


def _existing_template(title: str) -> dict:
    template = _missing_template(title)
    template["status"] = "existing"
    template["matching_template_ids"] = ["hevy-existing"]
    return template


def _ambiguous_template(title: str) -> dict:
    template = _missing_template(title)
    template["status"] = "ambiguous"
    template["matching_template_ids"] = ["hevy-a", "hevy-b"]
    return template
