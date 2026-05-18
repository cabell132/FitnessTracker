from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine

from fitness_tracker.cli import main
from fitness_tracker.database import Store
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.tracker import (
    Exercise,
    Sets,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem


def test_workout_backfill_review_cli_writes_deterministic_bundle_for_455045484(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)

    exit_code = main(
        [
            "sync-review",
            "truecoach-workout-backfill",
            "--workout-id",
            "455045484",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    bundle_dir = tmp_path / "reports" / "sync-review" / "truecoach-workout-backfill" / "455045484"
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    report = (bundle_dir / "report.md").read_text(encoding="utf-8")

    assert plan == {
        "blockers": [],
        "warnings": [],
        "workout": {
            "id": 455045484,
            "title": "Upper",
            "due": "2024-04-10T00:00:00",
            "state": "completed",
            "tracker_workout_id": 1,
            "tracker_hevy_app_id": None,
        },
        "items": [
            {
                "source_id": 8101,
                "tracker_workout_item_id": 1,
                "position": 1,
                "name": "Bench Press",
                "info": "3 x 8 @ 80kg",
                "comment": "80kg x 8, 80kg x 8, 80kg x 8",
                "selected_hevy_template": {
                    "id": "hevy-bench",
                    "name": "Bench Press",
                    "type": "weight_reps",
                    "equipment": "barbell",
                },
                "sets": [
                    {"type": "normal", "weight_kg": 80.0, "reps": 8},
                    {"type": "normal", "weight_kg": 80.0, "reps": 8},
                    {"type": "normal", "weight_kg": 80.0, "reps": 8},
                ],
                "notes": "",
                "warnings": [],
                "blockers": [],
            },
            {
                "source_id": 8102,
                "tracker_workout_item_id": 2,
                "position": 2,
                "name": "Chest Supported Row",
                "info": "2 x 10",
                "comment": "smooth reps",
                "selected_hevy_template": {
                    "id": "hevy-row",
                    "name": "Chest Supported Row",
                    "type": "weight_reps",
                    "equipment": "machine",
                },
                "sets": [
                    {"type": "normal", "weight_kg": 55.0, "reps": 10},
                    {"type": "normal", "weight_kg": 55.0, "reps": 10},
                ],
                "notes": "Athlete comment: smooth reps",
                "warnings": [],
                "blockers": [],
            },
        ],
    }
    assert request == {
        "workout": {
            "title": "2024-04-10 Upper",
            "description": "Backfill from True Coach Workout 455045484",
            "start_time": None,
            "end_time": None,
            "is_private": False,
            "exercises": [
                {
                    "exercise_template_id": "hevy-bench",
                    "superset_id": None,
                    "notes": None,
                    "sets": [
                        {
                            "type": "normal",
                            "weight_kg": 80.0,
                            "reps": 8,
                            "distance_meters": None,
                            "duration_seconds": None,
                            "rpe": None,
                        },
                        {
                            "type": "normal",
                            "weight_kg": 80.0,
                            "reps": 8,
                            "distance_meters": None,
                            "duration_seconds": None,
                            "rpe": None,
                        },
                        {
                            "type": "normal",
                            "weight_kg": 80.0,
                            "reps": 8,
                            "distance_meters": None,
                            "duration_seconds": None,
                            "rpe": None,
                        },
                    ],
                },
                {
                    "exercise_template_id": "hevy-row",
                    "superset_id": None,
                    "notes": "Athlete comment: smooth reps",
                    "sets": [
                        {
                            "type": "normal",
                            "weight_kg": 55.0,
                            "reps": 10,
                            "distance_meters": None,
                            "duration_seconds": None,
                            "rpe": None,
                        },
                        {
                            "type": "normal",
                            "weight_kg": 55.0,
                            "reps": 10,
                            "distance_meters": None,
                            "duration_seconds": None,
                            "rpe": None,
                        },
                    ],
                },
            ],
        }
    }
    assert "# True Coach Workout Backfill Review: 455045484" in report
    assert "Draft Hevy Workout request: hevy-workout-request.json" in report
    assert "Athlete comment: 80kg x 8, 80kg x 8, 80kg x 8" in report
    assert "Blockers: none" in report


def test_workout_backfill_review_reports_missing_hevy_template_mapping(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    with store.unit_of_work() as uow:
        exercise = uow.tracker.get_exercise(name="Chest Supported Row")
        assert exercise is not None
        exercise.hevy_app_id = None

    exit_code = main(
        [
            "sync-review",
            "truecoach-workout-backfill",
            "--workout-id",
            "455045484",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    bundle_dir = tmp_path / "reports" / "sync-review" / "truecoach-workout-backfill" / "455045484"
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    report = (bundle_dir / "report.md").read_text(encoding="utf-8")

    assert plan["blockers"] == [
        "Missing Hevy template mapping for performed item: Chest Supported Row"
    ]
    assert plan["items"][1]["selected_hevy_template"] is None
    assert [exercise["exercise_template_id"] for exercise in request["workout"]["exercises"]] == [
        "hevy-bench"
    ]
    assert (
        "BLOCKER: Missing Hevy template mapping for performed item: Chest Supported Row" in report
    )


def test_workout_backfill_review_omits_placeholder_rest_without_blocking(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_empty_backfill_item(store, {"name": "Rest", "info": "Rest"})

    exit_code = main(
        [
            "sync-review",
            "truecoach-workout-backfill",
            "--workout-id",
            "455045484",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    bundle_dir = tmp_path / "reports" / "sync-review" / "truecoach-workout-backfill" / "455045484"
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    report = (bundle_dir / "report.md").read_text(encoding="utf-8")

    assert plan["blockers"] == []
    assert plan["items"][2]["name"] == "Rest"
    assert plan["items"][2]["warnings"] == [
        "Placeholder rest item has no structured Sets rows; omitted from draft request."
    ]
    assert [exercise["exercise_template_id"] for exercise in request["workout"]["exercises"]] == [
        "hevy-bench",
        "hevy-row",
    ]
    assert "## 3. Rest" in report
    assert (
        "WARNING: Placeholder rest item has no structured Sets rows; omitted from draft request."
        in report
    )


def test_workout_backfill_review_defaults_down_regulate_to_duration_set(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    with store.unit_of_work() as uow:
        down_template = HevyAppExercise(
            id="hevy-down-regulate",
            name="Breathing",
            type="duration",
            equipment="none",
            default=False,
        )
        uow.session.add(down_template)
    _add_empty_backfill_item(
        store,
        {"name": "Down Regulate", "info": "Down regulate", "hevy_app_id": "hevy-down-regulate"},
    )

    exit_code = main(
        [
            "sync-review",
            "truecoach-workout-backfill",
            "--workout-id",
            "455045484",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    bundle_dir = tmp_path / "reports" / "sync-review" / "truecoach-workout-backfill" / "455045484"
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    report = (bundle_dir / "report.md").read_text(encoding="utf-8")

    assert plan["blockers"] == []
    assert plan["warnings"] == []
    assert plan["items"][2]["sets"] == [{"type": "normal", "duration_seconds": 240}]
    assert request["workout"]["exercises"][2] == {
        "exercise_template_id": "hevy-down-regulate",
        "superset_id": None,
        "notes": None,
        "sets": [
            {
                "type": "normal",
                "weight_kg": None,
                "reps": None,
                "distance_meters": None,
                "duration_seconds": 240,
                "rpe": None,
            }
        ],
    }
    assert "## 3. Down Regulate" in report
    assert "duration_seconds: 240" in report


def _add_empty_backfill_item(
    store: Store,
    item: dict[str, str | None],
) -> None:
    with store.unit_of_work() as uow:
        workout = uow.true_coach.get_workout(id=455045484).tracker
        assert workout is not None
        exercise = Exercise(name=item["name"], hevy_app_id=item.get("hevy_app_id"))
        uow.session.add(exercise)
        uow.session.add(
            TrueCoachWorkoutItem(
                id=8103,
                workout_id=455045484,
                name=item["name"],
                info=item["info"],
                comment="",
                is_circuit=False,
                state="completed",
                position=3,
                exercise_id=None,
                assessment_id=None,
            )
        )
        uow.session.flush()
        uow.session.add(
            TrackerWorkoutItem(
                workout_id=workout.id,
                position=3,
                exercise_id=exercise.id,
                true_coach_id=8103,
            )
        )


def _seed_backfill_review_workout(store: Store) -> None:  # noqa: PLR0915
    with store.unit_of_work() as uow:
        bench_template = HevyAppExercise(
            id="hevy-bench",
            name="Bench Press",
            type="weight_reps",
            equipment="barbell",
            default=False,
        )
        row_template = HevyAppExercise(
            id="hevy-row",
            name="Chest Supported Row",
            type="weight_reps",
            equipment="machine",
            default=False,
        )
        uow.session.add(bench_template)
        uow.session.add(row_template)
        uow.session.flush()
        bench = Exercise(name="Bench Press", hevy_app_id="hevy-bench")
        row = Exercise(name="Chest Supported Row", hevy_app_id="hevy-row")
        uow.session.add(bench)
        uow.session.add(row)
        uow.session.flush()
        due = datetime(2024, 4, 10, tzinfo=UTC)
        uow.session.add(
            TrueCoachWorkout(
                id=455045484,
                title="Upper",
                due=due,
                short_description="",
                state="completed",
                rest_day=False,
                created_at=due,
                updated_at=due,
            )
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=8101,
                workout_id=455045484,
                name="Bench Press",
                info="3 x 8 @ 80kg",
                comment="80kg x 8, 80kg x 8, 80kg x 8",
                is_circuit=False,
                state="completed",
                position=1,
                exercise_id=None,
                assessment_id=None,
            )
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=8102,
                workout_id=455045484,
                name="Chest Supported Row",
                info="2 x 10",
                comment="smooth reps",
                is_circuit=False,
                state="completed",
                position=2,
                exercise_id=None,
                assessment_id=None,
            )
        )
        tracker_workout = TrackerWorkout(
            title="Upper",
            description="",
            true_coach_id=455045484,
        )
        uow.session.add(tracker_workout)
        uow.session.flush()
        bench_item = TrackerWorkoutItem(
            workout_id=tracker_workout.id,
            position=1,
            exercise_id=bench.id,
            true_coach_id=8101,
        )
        row_item = TrackerWorkoutItem(
            workout_id=tracker_workout.id,
            position=2,
            exercise_id=row.id,
            true_coach_id=8102,
        )
        uow.session.add(bench_item)
        uow.session.add(row_item)
        uow.session.flush()
        for index in range(3):
            uow.session.add(
                Sets(
                    workout_item_id=bench_item.id,
                    index=index,
                    type="normal",
                    weight_kg=80.0,
                    reps=8,
                )
            )
        for index in range(2):
            uow.session.add(
                Sets(
                    workout_item_id=row_item.id,
                    index=index,
                    type="normal",
                    weight_kg=55.0,
                    reps=10,
                )
            )
