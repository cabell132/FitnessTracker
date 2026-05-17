from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine

from fitness_tracker.cli import main
from fitness_tracker.database import Store
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.tracker import Exercise as TrackerExercise
from fitness_tracker.database.models.true_coach import (
    TrueCoachExercise,
    TrueCoachWorkout,
    TrueCoachWorkoutItem,
)


def test_sync_review_cli_writes_ordered_report_and_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    reports_dir = tmp_path / "reports"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_workout(store)

    exit_code = main(
        [
            "sync-review",
            "truecoach-to-hevy",
            "--workout-id",
            "42",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(reports_dir),
        ]
    )

    assert exit_code == 0
    bundle_dir = reports_dir / "sync-review" / "truecoach-to-hevy" / "42"
    report = (bundle_dir / "report.md").read_text()
    plan = json.loads((bundle_dir / "plan.json").read_text())

    _assert_report(report)
    _assert_plan(plan)


def _assert_report(report: str) -> None:
    assert report.index("## 1. Bench Press") < report.index("## 2. Mystery Carry")
    assert "Source ID: 1001" in report
    assert "Info: 3 x 8 @ RPE 7" in report
    assert "Selected Hevy template: Barbell Bench Press (hevy-bench)" in report
    assert "- type: normal; reps: 8" in report
    assert "Source ID: 1002" in report
    assert "Selected Hevy template: unknown" in report
    assert "WARNING: No linked Hevy exercise template found." in report


def _assert_plan(plan: dict) -> None:
    assert plan["workout"]["id"] == 42
    assert [item["source_id"] for item in plan["items"]] == [1001, 1002]
    assert plan["items"][0]["selected_hevy_template"]["id"] == "hevy-bench"
    assert plan["items"][0]["proposed_sets"] == [
        {"type": "normal", "reps": 8},
        {"type": "normal", "reps": 8},
        {"type": "normal", "reps": 8},
    ]
    assert plan["items"][1]["warnings"] == ["No linked Hevy exercise template found."]


def _seed_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.add(
            TrueCoachWorkout(
                id=42,
                title="Upper Strength",
                due=now,
                short_description='<p class="name-and-info">A) Bench Press<br/>B) Mystery Carry</p>',
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.add(TrueCoachExercise(id=501, name="Bench Press", default=False))
        uow.add(
            HevyAppExercise(
                id="hevy-bench",
                name="Barbell Bench Press",
                type="weight_reps",
                equipment="barbell",
                default=True,
            )
        )
        uow.add(TrackerExercise(name="Bench Press", hevy_app_id="hevy-bench", true_coach_id=501))
        uow.add(
            TrueCoachWorkoutItem(
                id=1002,
                workout_id=42,
                name="Mystery Carry",
                info="walk heavy",
                comment="",
                is_circuit=False,
                state="pending",
                position=2,
                exercise_id=None,
                assessment_id=None,
            )
        )
        uow.add(
            TrueCoachWorkoutItem(
                id=1001,
                workout_id=42,
                name="Bench Press",
                info="3 x 8 @ RPE 7",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=501,
                assessment_id=None,
            )
        )
