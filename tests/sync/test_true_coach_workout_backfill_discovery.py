from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine

from fitness_tracker.cli import main
from fitness_tracker.database import Store
from fitness_tracker.database.models.hevy_app import HevyAppWorkout
from fitness_tracker.database.models.tracker import (
    Exercise,
    Sets,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem
from fitness_tracker.sync_review import WorkoutBackfillPipeline


def test_backfill_discovery_cli_reports_unlinked_completed_workout_candidates(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_candidates(store)

    exit_code = main(
        [
            "workout-backfill",
            "candidates",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    report_path = tmp_path / "reports" / "workout-backfill" / "candidates" / "report.md"
    json_path = report_path.with_name("candidates.json")

    report = report_path.read_text(encoding="utf-8")
    candidates = json.loads(json_path.read_text(encoding="utf-8"))

    assert candidates == [
        {
            "true_coach_id": 455045484,
            "due": "2024-04-10T00:00:00",
            "title": "Upper",
            "tracker_workout_id": 1,
            "workout_item_count": 2,
            "set_count": 3,
            "candidate_status": "structured-results",
        },
        {
            "true_coach_id": 455047508,
            "due": "2024-04-12T00:00:00",
            "title": "Wedding Dancing",
            "tracker_workout_id": 2,
            "workout_item_count": 1,
            "set_count": 0,
            "candidate_status": "placeholder-or-no-results",
        },
    ]
    assert (
        "| 455045484 | 2024-04-10T00:00:00 | Upper | 1 | 2 | 3 | structured-results |"
    ) in report
    assert (
        "| 455047508 | 2024-04-12T00:00:00 | Wedding Dancing | 2 | 1 | 0 | "
        "placeholder-or-no-results |"
    ) in report
    assert "455047509" not in report
    assert "455047510" not in report
    assert "455047511" not in report


def test_workout_backfill_candidates_pipeline_writes_manifest_contents(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_candidates(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")

    result = pipeline.candidates()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.directory == tmp_path / "reports" / "workout-backfill" / "candidates"
    assert result.report_path == result.directory / "report.md"
    assert result.candidates_path == result.directory / "candidates.json"
    assert result.manifest_path == result.directory / "candidates-manifest.json"
    assert result.candidate_count == 2
    assert manifest["workflow"] == "workout-backfill-candidates"
    assert manifest["schema_version"] == 1
    assert manifest["artifacts"] == {
        "report": "report.md",
        "candidates": "candidates.json",
    }


def test_workout_backfill_candidates_cli_writes_default_artifacts_and_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_candidates(store)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "workout-backfill",
            "candidates",
            "--database-url",
            f"sqlite:///{db_path}",
        ]
    )

    assert exit_code == 0
    candidates_dir = tmp_path / "reports" / "workout-backfill" / "candidates"
    manifest = json.loads((candidates_dir / "candidates-manifest.json").read_text(encoding="utf-8"))
    candidates = json.loads((candidates_dir / "candidates.json").read_text(encoding="utf-8"))
    report = (candidates_dir / "report.md").read_text(encoding="utf-8")

    assert manifest == {
        "workflow": "workout-backfill-candidates",
        "schema_version": 1,
        "generated_at": manifest["generated_at"],
        "artifacts": {
            "report": "report.md",
            "candidates": "candidates.json",
        },
    }
    assert isinstance(manifest["generated_at"], str)
    assert [candidate["true_coach_id"] for candidate in candidates] == [455045484, 455047508]
    assert "| 455045484 | 2024-04-10T00:00:00 | Upper |" in report


def _seed_backfill_candidates(store: Store) -> None:  # noqa: PLR0915
    with store.unit_of_work() as uow:
        exercise = Exercise(name="Bench Press")
        placeholder = Exercise(name="Wedding Dancing")
        uow.session.add(exercise)
        uow.session.add(placeholder)
        uow.session.flush()

        _add_true_coach_workout(
            uow,
            workout_id=455045484,
            title="Upper",
            due=datetime(2024, 4, 10, tzinfo=UTC),
            state="completed",
            rest_day=False,
            items=[
                TrueCoachWorkoutItem(
                    id=8101,
                    workout_id=455045484,
                    name="Bench Press",
                    info="3 x 8",
                    comment="80kg",
                    is_circuit=False,
                    state="completed",
                    position=1,
                    exercise_id=None,
                    assessment_id=None,
                ),
                TrueCoachWorkoutItem(
                    id=8102,
                    workout_id=455045484,
                    name="Row",
                    info="",
                    comment="",
                    is_circuit=False,
                    state="completed",
                    position=2,
                    exercise_id=None,
                    assessment_id=None,
                ),
            ],
        )
        structured_tracker = TrackerWorkout(
            title="Upper",
            description="",
            true_coach_id=455045484,
        )
        uow.session.add(structured_tracker)
        uow.session.flush()
        structured_item = TrackerWorkoutItem(
            workout_id=structured_tracker.id,
            position=1,
            exercise_id=exercise.id,
            true_coach_id=8101,
        )
        empty_item = TrackerWorkoutItem(
            workout_id=structured_tracker.id,
            position=2,
            exercise_id=exercise.id,
            true_coach_id=8102,
        )
        uow.session.add(structured_item)
        uow.session.add(empty_item)
        uow.session.flush()
        uow.session.add(Sets(workout_item_id=structured_item.id, index=0, type="normal", reps=8))
        uow.session.add(Sets(workout_item_id=structured_item.id, index=1, type="normal", reps=8))
        uow.session.add(Sets(workout_item_id=structured_item.id, index=2, type="normal", reps=8))

        _add_true_coach_workout(
            uow,
            workout_id=455047508,
            title="Wedding Dancing",
            due=datetime(2024, 4, 12, tzinfo=UTC),
            state="completed",
            rest_day=False,
            items=[
                TrueCoachWorkoutItem(
                    id=8201,
                    workout_id=455047508,
                    name="Wedding Dancing",
                    info="placeholder",
                    comment="",
                    is_circuit=False,
                    state="completed",
                    position=1,
                    exercise_id=None,
                    assessment_id=None,
                )
            ],
        )
        placeholder_tracker = TrackerWorkout(
            title="Wedding Dancing",
            description="",
            true_coach_id=455047508,
        )
        uow.session.add(placeholder_tracker)
        uow.session.flush()
        uow.session.add(
            TrackerWorkoutItem(
                workout_id=placeholder_tracker.id,
                position=1,
                exercise_id=placeholder.id,
                true_coach_id=8201,
            )
        )

        _add_true_coach_workout(
            uow,
            workout_id=455047509,
            title="Pending",
            due=datetime(2024, 4, 13, tzinfo=UTC),
            state="pending",
            rest_day=False,
            items=[],
        )
        _add_true_coach_workout(
            uow,
            workout_id=455047510,
            title="Rest",
            due=datetime(2024, 4, 14, tzinfo=UTC),
            state="completed",
            rest_day=True,
            items=[],
        )
        _add_true_coach_workout(
            uow,
            workout_id=455047511,
            title="Already Linked",
            due=datetime(2024, 4, 15, tzinfo=UTC),
            state="completed",
            rest_day=False,
            items=[],
        )
        uow.session.add(
            HevyAppWorkout(
                id="hevy-linked",
                title="Already Linked",
                description="",
                start_time=datetime(2024, 4, 15, tzinfo=UTC),
                end_time=datetime(2024, 4, 15, tzinfo=UTC),
                created_at=datetime(2024, 4, 15, tzinfo=UTC),
                updated_at=datetime(2024, 4, 15, tzinfo=UTC),
            )
        )
        uow.session.add(
            TrackerWorkout(
                title="Already Linked",
                description="",
                true_coach_id=455047511,
                hevy_app_id="hevy-linked",
            )
        )


def _add_true_coach_workout(  # noqa: PLR0913
    uow,
    *,
    workout_id: int,
    title: str,
    due: datetime,
    state: str,
    rest_day: bool,
    items: list[TrueCoachWorkoutItem],
) -> None:
    uow.session.add(
        TrueCoachWorkout(
            id=workout_id,
            title=title,
            due=due,
            short_description="",
            state=state,
            rest_day=rest_day,
            created_at=due,
            updated_at=due,
        )
    )
    for item in items:
        uow.session.add(item)
