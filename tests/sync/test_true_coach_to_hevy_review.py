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
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_workout(store)

    report, plan = _write_sync_review(tmp_path, db_path, workout_id=42)

    _assert_report(report)
    _assert_plan(plan)


def test_sync_review_reports_missing_single_leg_isometric_calf_raise_template(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_template_override_workout(store)

    report, plan = _write_sync_review(tmp_path, db_path, workout_id=43)

    assert "Selected Hevy template: Bodyweight Calf Raise (hevy-calf-raise)" in report
    assert "Required Hevy templates:" in report
    assert (
        "- Single-Leg Isometric Calf Raise | type: duration | equipment: bodyweight | "
        "muscle group: calves | other muscles: none | status: missing | source IDs: 1003"
    ) in report
    assert "BLOCKER: Missing required Hevy template: Single-Leg Isometric Calf Raise" in report

    item = plan["items"][0]
    assert item["selected_hevy_template"]["id"] == "hevy-calf-raise"
    assert item["required_hevy_templates"] == [
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
    assert item["blockers"] == ["Missing required Hevy template: Single-Leg Isometric Calf Raise"]


def test_sync_review_reports_ambiguous_isometric_knee_extension_template(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_template_override_workout(store)
    _seed_ambiguous_knee_extension_workout(store)

    report, plan = _write_sync_review(tmp_path, db_path, workout_id=44)

    assert "Selected Hevy template: Seated Knee Extension (hevy-knee-extension)" in report
    assert (
        "- Isometric Seated Knee Extension | type: duration | equipment: machine | "
        "muscle group: quadriceps | other muscles: none | status: ambiguous | source IDs: 1004"
    ) in report
    assert "BLOCKER: Ambiguous required Hevy template: Isometric Seated Knee Extension" in report

    item = plan["items"][0]
    assert item["selected_hevy_template"]["id"] == "hevy-knee-extension"
    assert item["required_hevy_templates"] == [
        {
            "title": "Isometric Seated Knee Extension",
            "expected_type": "duration",
            "equipment_category": "machine",
            "muscle_group": "quadriceps",
            "other_muscles": [],
            "status": "ambiguous",
            "source_workout_item_ids": [1004],
            "matching_template_ids": ["hevy-knee-iso-a", "hevy-knee-iso-b"],
        }
    ]
    assert item["blockers"] == ["Ambiguous required Hevy template: Isometric Seated Knee Extension"]


def test_sync_review_splits_mixed_iso_hold_and_reps_prescription(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_mixed_mode_knee_extension_workout(store)

    report, plan = _write_sync_review(tmp_path, db_path, workout_id=45)

    assert report.index("Block 1: Isometric hold") < report.index("Block 2: Dynamic reps")
    assert "BLOCKER: Missing required Hevy template: Isometric Seated Knee Extension" in report

    item = plan["items"][0]
    assert item["source_id"] == 1005
    _assert_mixed_knee_extension_blocks(item)
    assert item["blockers"] == ["Missing required Hevy template: Isometric Seated Knee Extension"]


def _assert_mixed_knee_extension_blocks(item: dict) -> None:
    blocks = item["planned_blocks"]
    assert [block["source_id"] for block in blocks] == [1005, 1005]
    assert [block["phase_kind"] for block in blocks] == ["isometric_hold", "dynamic_reps"]
    assert blocks[0]["source_text"] == "2 x 30s iso hold"
    assert blocks[0]["notes"] == "2 x 30s iso hold\nSource: 2 x 30s iso hold then 3 x 10-12"
    assert blocks[0]["selected_hevy_template"] is None
    assert blocks[0]["required_hevy_templates"] == [
        {
            "title": "Isometric Seated Knee Extension",
            "expected_type": "duration",
            "equipment_category": "machine",
            "muscle_group": "quadriceps",
            "other_muscles": [],
            "status": "missing",
            "source_workout_item_ids": [1005],
            "matching_template_ids": [],
        }
    ]
    assert blocks[0]["proposed_sets"] == [
        {"type": "normal", "duration_seconds": 30},
        {"type": "normal", "duration_seconds": 30},
    ]
    assert blocks[1]["source_text"] == "3 x 10-12"
    assert blocks[1]["selected_hevy_template"]["id"] == "hevy-knee-extension"
    assert blocks[1]["required_hevy_templates"] == []
    assert blocks[1]["proposed_sets"] == [
        {"type": "normal", "reps": 12},
        {"type": "normal", "reps": 12},
        {"type": "normal", "reps": 12},
    ]


def _write_sync_review(
    tmp_path: Path,
    db_path: Path,
    *,
    workout_id: int,
) -> tuple[str, dict]:
    reports_dir = tmp_path / "reports"
    exit_code = main(
        [
            "sync-review",
            "truecoach-to-hevy",
            "--workout-id",
            str(workout_id),
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(reports_dir),
        ]
    )

    assert exit_code == 0
    bundle_dir = reports_dir / "sync-review" / "truecoach-to-hevy" / str(workout_id)
    report = (bundle_dir / "report.md").read_text()
    plan = json.loads((bundle_dir / "plan.json").read_text())
    return report, plan


def _assert_report(report: str) -> None:
    assert report.index("## 1. Bench Press") < report.index("## 2. Mystery Carry")
    assert "Source ID: 1001" in report
    assert "Info: 3 x 10-12 ES ^Glternating RIR 2" in report
    assert "Selected Hevy template: Barbell Bench Press (hevy-bench)" in report
    assert "- type: normal; reps: 12" in report
    assert "Source ID: 1002" in report
    assert "Info: 3 x 8+8+8 ^Glternating RIR 1" in report
    assert "- type: dropset; reps: 8" in report
    assert "Selected Hevy template: unknown" in report
    assert "WARNING: No linked Hevy exercise template found." in report


def _assert_plan(plan: dict) -> None:
    assert plan["workout"]["id"] == 42
    assert [item["source_id"] for item in plan["items"]] == [1001, 1002]
    assert plan["items"][0]["selected_hevy_template"]["id"] == "hevy-bench"
    assert plan["items"][0]["proposed_sets"] == [
        {"type": "normal", "reps": 12},
        {"type": "normal", "reps": 12},
        {"type": "normal", "reps": 12},
    ]
    assert plan["items"][1]["proposed_sets"] == [
        {"type": "normal", "reps": 8},
        {"type": "dropset", "reps": 8},
        {"type": "dropset", "reps": 8},
        {"type": "normal", "reps": 8},
        {"type": "dropset", "reps": 8},
        {"type": "dropset", "reps": 8},
        {"type": "normal", "reps": 8},
        {"type": "dropset", "reps": 8},
        {"type": "dropset", "reps": 8},
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
                info="3 x 8+8+8 ^Glternating RIR 1",
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
                info="3 x 10-12 ES ^Glternating RIR 2",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=501,
                assessment_id=None,
            )
        )


def _seed_template_override_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.add(
            TrueCoachWorkout(
                id=43,
                title="Lower Strength",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.add(TrueCoachExercise(id=502, name="Bodyweight Calf Raise", default=False))
        uow.add(
            HevyAppExercise(
                id="hevy-calf-raise",
                name="Bodyweight Calf Raise",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.add(
            TrackerExercise(
                name="Bodyweight Calf Raise",
                hevy_app_id="hevy-calf-raise",
                true_coach_id=502,
            )
        )
        uow.add(
            TrueCoachWorkoutItem(
                id=1003,
                workout_id=43,
                name="Bodyweight Calf Raise",
                info="3 x 20s single leg iso hold ES",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=502,
                assessment_id=None,
            )
        )


def _seed_ambiguous_knee_extension_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.add(
            TrueCoachWorkout(
                id=44,
                title="Knee Rehab",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.add(TrueCoachExercise(id=503, name="Seated Knee Extension", default=False))
        uow.add(
            HevyAppExercise(
                id="hevy-knee-extension",
                name="Seated Knee Extension",
                type="reps_only",
                equipment="machine",
                default=True,
            )
        )
        uow.add(
            HevyAppExercise(
                id="hevy-knee-iso-a",
                name="Isometric Seated Knee Extension",
                type="duration",
                equipment="machine",
                default=False,
            )
        )
        uow.add(
            HevyAppExercise(
                id="hevy-knee-iso-b",
                name="Isometric Seated Knee Extension",
                type="duration",
                equipment="machine",
                default=False,
            )
        )
        uow.add(
            TrackerExercise(
                name="Seated Knee Extension",
                hevy_app_id="hevy-knee-extension",
                true_coach_id=503,
            )
        )
        uow.add(
            TrueCoachWorkoutItem(
                id=1004,
                workout_id=44,
                name="Seated Knee Extension",
                info="4 x 30s iso hold",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=503,
                assessment_id=None,
            )
        )


def _seed_mixed_mode_knee_extension_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.add(
            TrueCoachWorkout(
                id=45,
                title="Knee Rehab Mixed",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.add(TrueCoachExercise(id=504, name="Seated Knee Extension", default=False))
        uow.add(
            HevyAppExercise(
                id="hevy-knee-extension",
                name="Seated Knee Extension",
                type="reps_only",
                equipment="machine",
                default=True,
            )
        )
        uow.add(
            TrackerExercise(
                name="Seated Knee Extension",
                hevy_app_id="hevy-knee-extension",
                true_coach_id=504,
            )
        )
        uow.add(
            TrueCoachWorkoutItem(
                id=1005,
                workout_id=45,
                name="Seated Knee Extension",
                info="2 x 30s iso hold then 3 x 10-12",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=504,
                assessment_id=None,
            )
        )
