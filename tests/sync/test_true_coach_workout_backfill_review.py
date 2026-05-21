from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

from fitness_tracker import cli
from fitness_tracker.apis.hevy_app.types import (
    Exercise as HevyWorkoutExercise,
    PostWorkoutsRequestBody,
    PostWorkoutsResponse,
    Set as HevySet,
    Workout as HevyWorkout,
)
from fitness_tracker.cli import main
from fitness_tracker.database import Store
from fitness_tracker.database.models.apple_health import (
    AppleHealthDataRecord,
    AppleHealthDataType,
    AppleHealthWorkout,
    AppleHealthWorkoutType,
)
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.hevy_app import HevyAppSets, HevyAppWorkout, HevyAppWorkoutItem
from fitness_tracker.database.models.tracker import (
    Exercise,
    Sets,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem
from fitness_tracker.sync_review.true_coach_workout_backfill import (
    WorkoutBackfillApplyError,
    WorkoutBackfillPipeline,
    WorkoutBackfillReviewError,
    WorkoutBackfillReviewOptions,
    TrueCoachWorkoutBackfillReviewService,
)
from fitness_tracker.sync_review.workout_backfill_performed_work import (
    _omitted_movement_names,
    plan_performed_work_items,
)


def test_workout_backfill_review_cli_writes_deterministic_bundle_for_455045484(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)

    exit_code = main(
        [
            "workout-backfill",
            "review",
            "--workout-id",
            "455045484",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    bundle_dir = tmp_path / "reports" / "workout-backfill" / "455045484"
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
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
                "superset_id": 0,
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
                "superset_id": 0,
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
    assert "# True Coach Workout Backfill Review: 455045484" in report
    assert "Hevy Workout request: not written" in report
    assert "Athlete comment: 80kg x 8, 80kg x 8, 80kg x 8" in report
    assert "Blockers: none" in report
    assert not (bundle_dir / "hevy-workout-request.json").exists()


def test_workout_backfill_pipeline_review_writes_manifest_layout_without_request(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")

    result = pipeline.review(455045484)

    review_dir = tmp_path / "reports" / "workout-backfill" / "455045484"
    manifest = json.loads((review_dir / "review-manifest.json").read_text(encoding="utf-8"))
    assert result.directory == review_dir
    assert manifest == {
        "version": 1,
        "kind": "workout-backfill-review",
        "workout_id": 455045484,
        "artifacts": {
            "plan": "plan.json",
            "decisions": "decisions.json",
            "decision_validation": "decision-validation.json",
            "apple_health_evidence": "apple-health-evidence.json",
            "report": "report.md",
        },
        "request_status": "not-written",
    }
    assert (review_dir / "plan.json").exists()
    assert (review_dir / "decisions.json").exists()
    assert (review_dir / "decision-validation.json").exists()
    assert (review_dir / "apple-health-evidence.json").exists()
    assert (review_dir / "report.md").exists()
    assert not (review_dir / "hevy-workout-request.json").exists()
    assert not (review_dir / "request-manifest.json").exists()


def test_workout_backfill_pipeline_review_requires_force_for_existing_directory(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")

    pipeline.review(455045484)

    with pytest.raises(WorkoutBackfillReviewError, match="already exists"):
        pipeline.review(455045484)


def test_workout_backfill_pipeline_force_requires_decision_strategy(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)

    with pytest.raises(WorkoutBackfillReviewError, match="preserve-decisions"):
        pipeline.review(455045484, WorkoutBackfillReviewOptions(force=True))

    review.decisions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workout": {
                    "id": 999,
                    "selected_start_time": None,
                    "selected_end_time": None,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    preserved = pipeline.review(
        455045484,
        WorkoutBackfillReviewOptions(force=True, preserve_decisions=True),
    )
    decisions = json.loads(preserved.decisions_path.read_text(encoding="utf-8"))
    validation = json.loads(preserved.decision_validation_path.read_text(encoding="utf-8"))

    assert decisions["workout"]["id"] == 999
    assert validation["blockers"] == [
        "Decision workout id must match True Coach Workout 455045484",
        "Missing required decision: selected Workout timestamps",
    ]


def test_workout_backfill_pipeline_inspect_loads_artifacts_through_manifest(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    alternate_plan_path = review.directory / "renamed-plan.json"
    review.plan_path.rename(alternate_plan_path)
    manifest = json.loads(review.manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["plan"] = alternate_plan_path.name
    review.manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    result = pipeline.inspect(review.directory)

    assert result.review_dir == review.directory
    assert result.manifest["request_status"] == "not-written"
    assert result.plan["workout"]["id"] == 455045484
    assert result.decision_validation["blockers"] == [
        "Missing required decision: selected Workout timestamps"
    ]


def test_workout_backfill_pipeline_write_request_writes_request_and_manifest(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)

    result = pipeline.write_request(review.directory)

    request = json.loads(result.request_path.read_text(encoding="utf-8"))
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert request["workout"]["start_time"] == "2024-04-10T13:00:00+00:00"
    assert request["workout"]["end_time"] == "2024-04-10T14:00:00+00:00"
    assert manifest["workflow"] == "workout-backfill"
    assert manifest["schema_version"] == 1
    assert manifest["artifacts"] == {
        "plan": "plan.json",
        "decisions": "decisions.json",
        "decision_validation": "decision-validation.json",
        "request": "hevy-workout-request.json",
    }
    assert set(manifest["sha256"]) == {
        "plan",
        "decisions",
        "decision_validation",
        "request",
    }
    review_manifest = json.loads(review.manifest_path.read_text(encoding="utf-8"))
    assert review_manifest["request_status"] == "written"


def test_workout_backfill_pipeline_write_request_blocks_invalid_decisions(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)

    with pytest.raises(WorkoutBackfillApplyError, match="selected Workout timestamps"):
        pipeline.write_request(review.directory)

    assert not (review.directory / "hevy-workout-request.json").exists()
    assert not (review.directory / "request-manifest.json").exists()


def test_workout_backfill_pipeline_write_request_rewrites_stale_derived_request(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    first = pipeline.write_request(review.directory)
    request = json.loads(first.request_path.read_text(encoding="utf-8"))
    assert request["workout"]["start_time"] == "2024-04-10T13:00:00+00:00"
    decisions = json.loads(review.decisions_path.read_text(encoding="utf-8"))
    decisions["workout"]["selected_start_time"] = "2024-04-10T15:00:00+00:00"
    review.decisions_path.write_text(json.dumps(decisions) + "\n", encoding="utf-8")

    result = pipeline.write_request(review.directory)

    rewritten = json.loads(result.request_path.read_text(encoding="utf-8"))
    assert rewritten["workout"]["start_time"] == "2024-04-10T15:00:00+00:00"


def test_workout_backfill_pipeline_write_request_rejects_manual_edit_unless_forced(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    result = pipeline.write_request(review.directory)
    request = json.loads(result.request_path.read_text(encoding="utf-8"))
    request["workout"]["title"] = "Manual Edit"
    result.request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")

    with pytest.raises(WorkoutBackfillReviewError, match="use --force"):
        pipeline.write_request(review.directory)

    forced = pipeline.write_request(review.directory, force=True)
    overwritten = json.loads(forced.request_path.read_text(encoding="utf-8"))
    assert overwritten["workout"]["title"] == "2024-04-10 Upper"


def test_workout_backfill_pipeline_write_request_requires_workout_backfill_manifest(
    tmp_path: Path,
) -> None:
    review_dir = tmp_path / "review"
    review_dir.mkdir()
    (review_dir / "review-manifest.json").write_text(
        json.dumps({"version": 1, "kind": "other-review", "artifacts": {}}) + "\n",
        encoding="utf-8",
    )
    pipeline = WorkoutBackfillPipeline(
        store=Store(create_engine("sqlite:///:memory:")),
        output_root=tmp_path / "reports",
    )

    with pytest.raises(WorkoutBackfillReviewError, match="not a Workout backfill review"):
        pipeline.write_request(review_dir)


def test_workout_backfill_pipeline_diff_reads_manifest_verified_request(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    request = pipeline.write_request(review.directory)
    _seed_linked_local_hevy_workout(store, title="Edited Upper")
    original_request = request.request_path.read_text(encoding="utf-8")
    original_manifest = request.manifest_path.read_text(encoding="utf-8")

    result = pipeline.diff(review.directory)

    assert result.request_path == request.request_path
    assert result.local_hevy_workout_id == "hevy-linked-455045484"
    assert result.differences == ["title request='2024-04-10 Upper' local='Edited Upper'"]
    assert request.request_path.read_text(encoding="utf-8") == original_request
    assert request.manifest_path.read_text(encoding="utf-8") == original_manifest


def test_workout_backfill_pipeline_diff_requires_written_request(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)

    with pytest.raises(WorkoutBackfillReviewError, match="write-request --review-dir"):
        pipeline.diff(review.directory)


def test_workout_backfill_pipeline_diff_rejects_stale_request_manifest(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    pipeline.write_request(review.directory)
    plan = json.loads(review.plan_path.read_text(encoding="utf-8"))
    plan["workout"]["title"] = "Stale Upper"
    review.plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")

    with pytest.raises(WorkoutBackfillReviewError, match="Request artifact is stale"):
        pipeline.diff(review.directory)


def test_workout_backfill_pipeline_diff_rejects_manual_request_edit(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    request = pipeline.write_request(review.directory)
    payload = json.loads(request.request_path.read_text(encoding="utf-8"))
    payload["workout"]["title"] = "Manual Upper"
    request.request_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(WorkoutBackfillReviewError, match="manual workflow"):
        pipeline.diff(review.directory)


def test_workout_backfill_pipeline_diff_requires_linked_local_hevy_workout(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    pipeline.write_request(review.directory)

    with pytest.raises(WorkoutBackfillReviewError, match="No linked local Hevy Workout"):
        pipeline.diff(review.directory)


def test_workout_backfill_pipeline_apply_submits_manifest_verified_request(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    request = pipeline.write_request(review.directory)
    request_contents = request.request_path.read_text(encoding="utf-8")
    writer = _RecordingWorkoutWriter(
        response=_hevy_workout_response(workout_id="hevy-created-455045484")
    )

    result = pipeline.apply(review.directory, workout_writer=writer)

    assert result.action == "created"
    assert result.request_path == request.request_path
    assert len(writer.requests) == 1
    assert writer.requests[0].workout.start_time == "2024-04-10T13:00:00+00:00"
    assert request.request_path.read_text(encoding="utf-8") == request_contents
    _assert_455045484_local_links(store)


def test_workout_backfill_pipeline_apply_rejects_request_hash_mismatch_before_mutation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    request = pipeline.write_request(review.directory)
    request_body = json.loads(request.request_path.read_text(encoding="utf-8"))
    request_body["workout"]["title"] = "Tampered Backfill"
    request.request_path.write_text(json.dumps(request_body) + "\n", encoding="utf-8")
    writer = _RecordingWorkoutWriter(
        response=_hevy_workout_response(workout_id="hevy-created-455045484")
    )

    with pytest.raises(WorkoutBackfillReviewError, match="hash mismatch"):
        pipeline.apply(review.directory, workout_writer=writer)

    assert writer.requests == []
    with store.unit_of_work() as uow:
        tracker_workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert tracker_workout is not None
        assert tracker_workout.hevy_app_id is None


def test_workout_backfill_pipeline_apply_rejects_stale_inputs_before_mutation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    pipeline.write_request(review.directory)
    decisions = json.loads(review.decisions_path.read_text(encoding="utf-8"))
    decisions["workout"]["selected_start_time"] = "2024-04-10T16:00:00+00:00"
    review.decisions_path.write_text(json.dumps(decisions) + "\n", encoding="utf-8")
    writer = _RecordingWorkoutWriter()

    with pytest.raises(WorkoutBackfillReviewError, match="Request artifact is stale"):
        pipeline.apply(review.directory, workout_writer=writer)

    assert writer.requests == []
    with store.unit_of_work() as uow:
        tracker_workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert tracker_workout is not None
        assert tracker_workout.hevy_app_id is None


def test_workout_backfill_pipeline_link_workout_links_existing_remote_from_artifacts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    pipeline.write_request(review.directory)
    writer = _RecordingWorkoutWriter(
        existing_workout=_hevy_workout_response(workout_id="hevy-existing-455045484").workout[0],
    )

    result = pipeline.link_workout(review.directory, workout_writer=writer)

    assert result.action == "linked_existing_workout"
    assert writer.requests == []
    assert writer.marker_searches == [455045484]
    assert result.request_path == review.directory / "hevy-workout-request.json"
    with store.unit_of_work() as uow:
        tracker_workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert tracker_workout is not None
        assert tracker_workout.hevy_app_id == "hevy-existing-455045484"


def test_workout_backfill_pipeline_link_workout_rejects_stale_request_artifact(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    pipeline.write_request(review.directory)
    request_path = review.directory / "hevy-workout-request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["workout"]["title"] = "Edited after manifest"
    request_path.write_text(json.dumps(request) + "\n", encoding="utf-8")
    writer = _RecordingWorkoutWriter(
        existing_workout=_hevy_workout_response(workout_id="hevy-existing-455045484").workout[0],
    )

    with pytest.raises(WorkoutBackfillReviewError, match="hash mismatch"):
        pipeline.link_workout(review.directory, workout_writer=writer)

    assert writer.requests == []
    assert writer.marker_searches == []


def test_workout_backfill_pipeline_link_workout_rejects_stale_decisions_artifact(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    pipeline.write_request(review.directory)
    decisions = json.loads(review.decisions_path.read_text(encoding="utf-8"))
    decisions["workout"]["selected_start_time"] = "2024-04-10T15:00:00+00:00"
    review.decisions_path.write_text(json.dumps(decisions) + "\n", encoding="utf-8")
    writer = _RecordingWorkoutWriter(
        existing_workout=_hevy_workout_response(workout_id="hevy-existing-455045484").workout[0],
    )

    with pytest.raises(WorkoutBackfillReviewError, match="Request artifact is stale"):
        pipeline.link_workout(review.directory, workout_writer=writer)

    assert writer.requests == []
    assert writer.marker_searches == []


def test_workout_backfill_pipeline_link_workout_rejects_missing_remote_marker_or_link(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    pipeline.write_request(review.directory)
    writer = _RecordingWorkoutWriter()

    with pytest.raises(WorkoutBackfillApplyError, match="No linked or marked remote Hevy Workout"):
        pipeline.link_workout(review.directory, workout_writer=writer)

    assert writer.requests == []
    assert writer.marker_searches == [455045484]


def test_workout_backfill_review_and_inspect_cli_smoke(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)

    review_exit_code = main(
        [
            "workout-backfill",
            "review",
            "--workout-id",
            "455045484",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )
    review_output = capsys.readouterr().out
    review_dir = tmp_path / "reports" / "workout-backfill" / "455045484"
    inspect_exit_code = main(
        [
            "workout-backfill",
            "inspect",
            "--review-dir",
            str(review_dir),
        ]
    )
    inspect_output = capsys.readouterr().out

    assert review_exit_code == 0
    assert f"Wrote Workout backfill review: {review_dir}" in review_output
    assert inspect_exit_code == 0
    assert f"review_dir: {review_dir}" in inspect_output
    assert "request_status: not-written" in inspect_output
    assert "workout: 455045484 | Upper" in inspect_output


def test_workout_backfill_write_request_cli_smoke(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)

    exit_code = main(
        [
            "workout-backfill",
            "write-request",
            "--review-dir",
            str(review.directory),
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert (
        f"Wrote Workout backfill request: {review.directory / 'hevy-workout-request.json'}"
        in output
    )
    assert (review.directory / "request-manifest.json").exists()


def test_workout_backfill_diff_cli_reports_differences(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    pipeline.write_request(review.directory)
    _seed_linked_local_hevy_workout(store, title="Edited Upper")

    exit_code = main(
        [
            "workout-backfill",
            "diff",
            "--review-dir",
            str(review.directory),
            "--database-url",
            f"sqlite:///{db_path}",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert f"request: {review.directory / 'hevy-workout-request.json'}" in output
    assert "local_hevy_workout: hevy-linked-455045484" in output
    assert "- title request='2024-04-10 Upper' local='Edited Upper'" in output


def test_workout_backfill_diff_cli_returns_zero_for_no_differences(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    pipeline.write_request(review.directory)
    _seed_linked_local_hevy_workout(store)

    exit_code = main(
        [
            "workout-backfill",
            "diff",
            "--review-dir",
            str(review.directory),
            "--database-url",
            f"sqlite:///{db_path}",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "No differences between request and linked local Hevy Workout cache." in output


def test_workout_backfill_apply_and_apply_manual_cli_smoke(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    request = pipeline.write_request(review.directory)
    fake_client = _FakeHevyWorkoutClient(
        response=_hevy_workout_response(workout_id="hevy-created-455045484")
    )
    monkeypatch.setattr(cli, "_hevy_client_from_config", lambda: fake_client)

    apply_exit_code = main(
        [
            "workout-backfill",
            "apply",
            "--review-dir",
            str(review.directory),
            "--database-url",
            f"sqlite:///{db_path}",
        ]
    )
    apply_output = capsys.readouterr().out
    manual_exit_code = main(
        [
            "workout-backfill",
            "apply-manual",
            "--workout-id",
            "455045484",
            "--request-path",
            str(request.request_path),
        ]
    )
    manual_output = capsys.readouterr().out

    assert apply_exit_code == 0
    assert f"Created Hevy Workout from request: {request.request_path}" in apply_output
    assert manual_exit_code == 0
    assert f"Created Hevy Workout from request: {request.request_path}" in manual_output
    assert len(fake_client.workouts.created_requests) == 2


def test_workout_backfill_link_workout_cli_smoke(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    pipeline = WorkoutBackfillPipeline(store=store, output_root=tmp_path / "reports")
    review = pipeline.review(455045484)
    _write_requestable_pipeline_decisions(review.decisions_path)
    pipeline.write_request(review.directory)
    writer = _RecordingWorkoutWriter(
        existing_workout=_hevy_workout_response(workout_id="hevy-existing-455045484").workout[0],
    )
    monkeypatch.setattr(cli, "_hevy_client_from_config", lambda: object())
    monkeypatch.setattr(cli, "HevyWorkoutWriterAdapter", lambda _client: writer)

    exit_code = main(
        [
            "workout-backfill",
            "link-workout",
            "--review-dir",
            str(review.directory),
            "--database-url",
            f"sqlite:///{db_path}",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert (
        f"Linked existing Workout from request: {review.directory / 'hevy-workout-request.json'}"
        in output
    )
    assert writer.requests == []


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

    bundle_dir = _write_backfill_review(db_path, tmp_path)
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

    bundle_dir = _write_backfill_review(db_path, tmp_path)
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

    bundle_dir = _write_backfill_review(db_path, tmp_path)
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


def test_workout_backfill_duration_item_uses_athlete_comment_when_sets_are_missing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(store, [("hevy-cross-trainer", "Cross Trainer")])
    _add_empty_backfill_item(
        store,
        {
            "name": "Cross Trainer",
            "info": "For as you have left",
            "comment": "43mins/503kcals\n12min walk",
            "hevy_app_id": "hevy-cross-trainer",
        },
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))

    assert plan["warnings"] == []
    assert plan["items"][2]["sets"] == [{"type": "normal", "duration_seconds": 2580}]
    assert plan["items"][2]["notes"] == "Athlete comment: 503kcals; 12min walk"
    assert request["workout"]["exercises"][2] == {
        "exercise_template_id": "hevy-cross-trainer",
        "superset_id": None,
        "notes": "Athlete comment: 503kcals; 12min walk",
        "sets": [
            {
                "type": "normal",
                "weight_kg": None,
                "reps": None,
                "distance_meters": None,
                "duration_seconds": 2580,
                "rpe": None,
            }
        ],
    }


def test_workout_backfill_distance_items_keep_app_visible_prescription_notes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_distance_backfill_item(store)

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))

    assert request["workout"]["exercises"][2]["notes"] == "Coach prescription: 3 x 200m"
    assert request["workout"]["exercises"][2]["sets"] == [
        {
            "type": "normal",
            "weight_kg": None,
            "reps": None,
            "distance_meters": 200,
            "duration_seconds": 60,
            "rpe": None,
        },
        {
            "type": "normal",
            "weight_kg": None,
            "reps": None,
            "distance_meters": 200,
            "duration_seconds": 60,
            "rpe": None,
        },
        {
            "type": "normal",
            "weight_kg": None,
            "reps": None,
            "distance_meters": 200,
            "duration_seconds": 60,
            "rpe": None,
        },
    ]


def test_workout_backfill_review_writes_apple_health_evidence_for_complete_cluster(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _seed_apple_health_evidence(
        store,
        workouts=[
            (
                "Traditional Strength Training",
                "2024-04-10T17:05:00+00:00",
                "2024-04-10T18:02:00+00:00",
            ),
            ("Outdoor Walk", "2024-04-09T12:00:00+00:00", "2024-04-09T12:35:00+00:00"),
        ],
        heart_rates=[
            ("2024-04-10T16:50:00+00:00", 82),
            ("2024-04-10T17:05:00+00:00", 116),
            ("2024-04-10T17:20:00+00:00", 142),
            ("2024-04-10T17:40:00+00:00", 151),
            ("2024-04-10T18:00:00+00:00", 126),
            ("2024-04-10T18:20:00+00:00", 88),
        ],
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    evidence = json.loads((bundle_dir / "apple-health-evidence.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    report = (bundle_dir / "report.md").read_text(encoding="utf-8")

    assert request["workout"]["start_time"] is None
    assert request["workout"]["end_time"] is None
    assert evidence == {
        "true_coach_due_date": "2024-04-10",
        "search_window": {
            "start": "2024-04-09T00:00:00",
            "end": "2024-04-11T23:59:59",
        },
        "workout_intervals": [
            {
                "type": "Outdoor Walk",
                "start": "2024-04-09T12:00:00",
                "end": "2024-04-09T12:35:00",
                "duration_minutes": 35.0,
            },
            {
                "type": "Traditional Strength Training",
                "start": "2024-04-10T17:05:00",
                "end": "2024-04-10T18:02:00",
                "duration_minutes": 57.0,
            },
        ],
        "heart_rate_summaries": [
            {
                "window_start": "2024-04-10T16:35:00",
                "window_end": "2024-04-10T18:32:00",
                "sample_count": 6,
                "average_bpm": 117.5,
                "max_bpm": 151.0,
            }
        ],
        "candidate_windows": [
            {
                "source": "apple_workout_interval",
                "confidence": "high",
                "start": "2024-04-10T17:05:00",
                "end": "2024-04-10T18:02:00",
                "reason": "Apple Health workout interval with elevated heart-rate samples.",
            }
        ],
    }
    assert "Apple Health evidence: apple-health-evidence.json" in report
    assert "Candidate timing windows:" in report


def test_workout_backfill_review_includes_incomplete_apple_health_cluster(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _seed_apple_health_evidence(
        store,
        workouts=[
            (
                "Functional Strength Training",
                "2024-04-10T06:15:00+00:00",
                "2024-04-10T06:48:00+00:00",
            )
        ],
        heart_rates=[],
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    evidence = json.loads((bundle_dir / "apple-health-evidence.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))

    assert request["workout"]["start_time"] is None
    assert request["workout"]["end_time"] is None
    assert evidence["workout_intervals"] == [
        {
            "type": "Functional Strength Training",
            "start": "2024-04-10T06:15:00",
            "end": "2024-04-10T06:48:00",
            "duration_minutes": 33.0,
        }
    ]
    assert evidence["heart_rate_summaries"] == []
    assert evidence["candidate_windows"] == [
        {
            "source": "apple_workout_interval",
            "confidence": "medium",
            "start": "2024-04-10T06:15:00",
            "end": "2024-04-10T06:48:00",
            "reason": "Apple Health workout interval on the True Coach due date.",
        }
    ]


def test_workout_backfill_review_finds_heart_rate_only_candidate(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _seed_apple_health_evidence(
        store,
        workouts=[],
        heart_rates=[
            ("2024-04-10T14:50:00+00:00", 78),
            ("2024-04-10T15:05:00+00:00", 124),
            ("2024-04-10T15:20:00+00:00", 138),
            ("2024-04-10T15:35:00+00:00", 146),
            ("2024-04-10T15:50:00+00:00", 132),
            ("2024-04-10T16:10:00+00:00", 84),
        ],
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    evidence = json.loads((bundle_dir / "apple-health-evidence.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))

    assert request["workout"]["start_time"] is None
    assert request["workout"]["end_time"] is None
    assert evidence["workout_intervals"] == []
    assert evidence["heart_rate_summaries"] == [
        {
            "window_start": "2024-04-10T15:05:00",
            "window_end": "2024-04-10T15:50:00",
            "sample_count": 4,
            "average_bpm": 135.0,
            "max_bpm": 146.0,
        }
    ]
    assert evidence["candidate_windows"] == [
        {
            "source": "heart_rate_block",
            "confidence": "medium",
            "start": "2024-04-10T15:05:00",
            "end": "2024-04-10T15:50:00",
            "reason": "Elevated heart-rate block without a matching Apple Health workout interval.",
        }
    ]


def test_workout_backfill_review_leaves_no_confidence_timing_unset(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _seed_apple_health_evidence(
        store,
        workouts=[],
        heart_rates=[
            ("2024-04-10T09:00:00+00:00", 72),
            ("2024-04-10T12:00:00+00:00", 76),
            ("2024-04-10T18:00:00+00:00", 80),
        ],
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    evidence = json.loads((bundle_dir / "apple-health-evidence.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    decisions = json.loads((bundle_dir / "decisions.json").read_text(encoding="utf-8"))
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))

    assert request["workout"]["start_time"] is None
    assert request["workout"]["end_time"] is None
    assert evidence["heart_rate_summaries"] == []
    assert evidence["candidate_windows"] == []
    assert decisions == {
        "version": 1,
        "workout": {
            "id": 455045484,
            "selected_start_time": None,
            "selected_end_time": None,
        },
    }
    assert validation == {
        "blockers": ["Missing required decision: selected Workout timestamps"],
        "warnings": [],
    }


def test_workout_backfill_review_applies_editable_timestamp_decisions(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workout": {
                    "id": 455045484,
                    "selected_start_time": "2024-04-10T17:05:00Z",
                    "selected_end_time": "2024-04-10T18:02:00Z",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = _run_backfill_review(tmp_path, 455045484, decisions_path)

    assert exit_code == 0
    bundle_dir = tmp_path / "reports" / "workout-backfill" / "455045484"
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))

    assert request["workout"]["start_time"] == "2024-04-10T17:05:00Z"
    assert request["workout"]["end_time"] == "2024-04-10T18:02:00Z"
    assert validation == {"blockers": [], "warnings": []}
    assert "decisions" not in plan
    assert "selected_start_time" not in plan["workout"]


def test_workout_backfill_choice_item_converts_single_performed_modality(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(store, [("hevy-cycle", "Cycle")])
    _add_choice_backfill_item(
        store,
        info="Cycle, Cross Trainer, Stairmaster or a Combination",
        comment="Cycle 20mins, 150 calories",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))

    choice_item = plan["items"][2]
    assert plan["blockers"] == []
    assert choice_item["name"] == "Cycle"
    assert choice_item["selected_hevy_template"] == {
        "id": "hevy-cycle",
        "name": "Cycle",
        "type": "duration",
        "equipment": "machine",
    }
    assert choice_item["sets"] == [{"type": "normal", "duration_seconds": 1200}]
    assert choice_item["notes"] == "Athlete comment: 150 calories"
    assert request["workout"]["exercises"][2] == {
        "exercise_template_id": "hevy-cycle",
        "superset_id": None,
        "notes": "Athlete comment: 150 calories",
        "sets": [
            {
                "type": "normal",
                "weight_kg": None,
                "reps": None,
                "distance_meters": None,
                "duration_seconds": 1200,
                "rpe": None,
            }
        ],
    }


def test_performed_work_planner_keeps_feedback_without_duplicating_structured_set_lines(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    with store.unit_of_work() as uow:
        item = uow.true_coach.get_workout_item(id=8101)
        item.comment = (
            "10x30\n10x30\n10x30\n\nNote: I got a wee bit of sharp pain in my mid left back"
        )
        tracker_item = item.tracker
        assert tracker_item is not None
        for set_row in tracker_item.sets:
            set_row.weight_kg = 30.0
            set_row.reps = 10

    with store.unit_of_work() as uow:
        workout = uow.true_coach.get_workout(id=455045484)
        assert isinstance(workout.tracker, TrackerWorkout)
        tracker_items = sorted(
            workout.tracker.workout_items,
            key=lambda item: (item.position, item.id),
        )
        templates = list(
            uow.session.execute(select(HevyAppExercise).order_by(HevyAppExercise.name)).scalars()
        )

        items = plan_performed_work_items(
            tracker_items,
            templates,
            superset_ids_by_position={},
        )

    assert items[0].notes == (
        "Athlete comment: Note: I got a wee bit of sharp pain in my mid left back"
    )


def test_performed_work_planner_converts_choice_item_without_review_service(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(store, [("hevy-cycle", "Cycle")])
    _add_choice_backfill_item(
        store,
        info="Cycle, Cross Trainer, Stairmaster or a Combination",
        comment="Cycle 20mins, 150 calories",
    )

    with store.unit_of_work() as uow:
        workout = uow.true_coach.get_workout(id=455045484)
        assert isinstance(workout.tracker, TrackerWorkout)
        tracker_items = sorted(
            workout.tracker.workout_items,
            key=lambda item: (item.position, item.id),
        )
        templates = list(
            uow.session.execute(select(HevyAppExercise).order_by(HevyAppExercise.name)).scalars()
        )

        items = plan_performed_work_items(
            tracker_items,
            templates,
            superset_ids_by_position={},
        )

    choice_item = items[2]
    assert choice_item.name == "Cycle"
    assert choice_item.selected_hevy_template is not None
    assert choice_item.selected_hevy_template.id == "hevy-cycle"
    assert [set_row.model_dump(exclude_none=True) for set_row in choice_item.sets] == [
        {"type": "normal", "duration_seconds": 1200}
    ]
    assert choice_item.notes == "Athlete comment: 150 calories"


def test_workout_backfill_choice_item_splits_multiple_performed_modalities(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(
        store,
        [
            ("hevy-cycle", "Cycle"),
            ("hevy-stairmaster", "Stairmaster"),
        ],
    )
    _add_choice_backfill_item(
        store,
        info="Cycle, Cross Trainer, Stairmaster or a Combination",
        comment="Stairmaster 10mins, Cycle 20mins, 1840 steps, 250 calories",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))

    assert plan["blockers"] == []
    assert [item["name"] for item in plan["items"][2:]] == ["Stairmaster", "Cycle"]
    assert [item["sets"] for item in plan["items"][2:]] == [
        [{"type": "normal", "duration_seconds": 600}],
        [{"type": "normal", "duration_seconds": 1200}],
    ]
    assert [exercise["exercise_template_id"] for exercise in request["workout"]["exercises"]] == [
        "hevy-bench",
        "hevy-row",
        "hevy-stairmaster",
        "hevy-cycle",
    ]
    assert request["workout"]["exercises"][2]["notes"] == (
        "Athlete comment: 1840 steps, 250 calories"
    )
    assert request["workout"]["exercises"][3]["notes"] == (
        "Athlete comment: 1840 steps, 250 calories"
    )


def test_workout_backfill_choice_item_uses_name_options_and_cardio_template_aliases(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(
        store,
        [
            ("hevy-cycle", "Cycling"),
            ("hevy-stairs", "Stair Machine"),
        ],
    )
    _add_choice_backfill_item(
        store,
        name="Cycle, Cross Trainer, Stairmaster or a Combination",
        info="For as long as you have left",
        comment="Stairs 10mins/663 steps\nCycle 20mins/193kcal",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))

    assert plan["blockers"] == []
    assert [item["name"] for item in plan["items"][2:]] == ["Stairmaster", "Cycle"]
    assert [item["sets"] for item in plan["items"][2:]] == [
        [{"type": "normal", "duration_seconds": 600}],
        [{"type": "normal", "duration_seconds": 1200}],
    ]
    assert [item["split_choice_performance"] for item in plan["items"][2:]] == [True, True]
    assert [exercise["exercise_template_id"] for exercise in request["workout"]["exercises"]] == [
        "hevy-bench",
        "hevy-row",
        "hevy-stairs",
        "hevy-cycle",
    ]


def test_workout_backfill_circuit_item_expands_performed_movements(  # noqa: PLR0915
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(
        store,
        [
            ("hevy-bike", "Bike"),
            ("hevy-burpees", "Burpees"),
            ("hevy-plank", "Plank"),
        ],
    )
    _add_circuit_backfill_item(
        store,
        info="3 Rounds\n10 Burpees\n15 cals Bike\nPlank 30s",
        comment="2 min 10 sec\n2 min 15 sec\nW/o Bike",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    report = (bundle_dir / "report.md").read_text(encoding="utf-8")

    circuit_items = plan["items"][2:]
    assert [item["name"] for item in circuit_items] == ["Burpees", "Bike", "Plank"]
    assert [item["movement_target"] for item in circuit_items] == ["10", "15 cals", "30s"]
    assert [item["completed_round_count"] for item in circuit_items] == [2, 2, 2]
    assert circuit_items[0]["sets"] == [
        {"type": "normal", "reps": 10},
        {"type": "normal", "reps": 10},
    ]
    assert circuit_items[1]["sets"] == []
    assert circuit_items[1]["warnings"] == ["Athlete comment omits Circuit movement: W/o Bike"]
    assert circuit_items[2]["sets"] == [
        {"type": "normal", "duration_seconds": 30},
        {"type": "normal", "duration_seconds": 30},
    ]
    assert "Completed round times: 2 min 10 sec; 2 min 15 sec" in circuit_items[0]["notes"]
    assert "2 min 10 sec" not in json.dumps(circuit_items[0]["sets"])
    assert [exercise["exercise_template_id"] for exercise in request["workout"]["exercises"]] == [
        "hevy-bench",
        "hevy-row",
        "hevy-burpees",
        "hevy-plank",
    ]
    assert "Movement target: 15 cals" in report
    assert "WARNING: Athlete comment omits Circuit movement: W/o Bike" in report


def test_workout_backfill_amrap_item_generates_request_exercises_with_shared_superset(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(store, [("hevy-bike", "Bike"), ("hevy-burpees", "Burpees")])
    _add_circuit_backfill_item(
        store,
        name="12' AMRAP",
        info="20 Bike\n10 Burpees",
        comment="2 min 10 sec\n2 min 15 sec",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))

    exercises = request["workout"]["exercises"]
    assert [exercise["exercise_template_id"] for exercise in exercises] == [
        "hevy-bench",
        "hevy-row",
        "hevy-bike",
        "hevy-burpees",
    ]
    assert [exercise["superset_id"] for exercise in exercises] == [0, 0, 1, 1]
    assert [(set_row["type"], set_row["reps"]) for set_row in exercises[2]["sets"]] == [
        ("normal", 20),
        ("normal", 20),
    ]
    assert [(set_row["type"], set_row["reps"]) for set_row in exercises[3]["sets"]] == [
        ("normal", 10),
        ("normal", 10),
    ]
    assert "AMRAP time cap seconds: 720" in exercises[2]["notes"]
    assert "Completed round times: 2 min 10 sec; 2 min 15 sec" in exercises[2]["notes"]


def test_workout_backfill_missed_amrap_item_does_not_expand_performed_work(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(store, [("hevy-bike", "Bike"), ("hevy-burpees", "Burpees")])
    _add_circuit_backfill_item(
        store,
        name="12' AMRAP",
        info="20 cal Bike\n10 Burpees",
        comment="",
        state="missed",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))

    assert [item["source_id"] for item in plan["items"]] == [8101, 8102]
    assert [exercise["exercise_template_id"] for exercise in request["workout"]["exercises"]] == [
        "hevy-bench",
        "hevy-row",
    ]


def test_workout_backfill_circuit_round_count_can_come_from_athlete_comment(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(store, [("hevy-burpees", "Burpees"), ("hevy-plank", "Plank")])
    _add_circuit_backfill_item(
        store,
        info="10 Burpees\nPlank 30s",
        comment="3 Rounds",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))

    circuit_items = plan["items"][2:]
    assert [item["completed_round_count"] for item in circuit_items] == [3, 3]
    assert circuit_items[0]["sets"] == [
        {"type": "normal", "reps": 10},
        {"type": "normal", "reps": 10},
        {"type": "normal", "reps": 10},
    ]
    assert circuit_items[1]["sets"] == [
        {"type": "normal", "duration_seconds": 30},
        {"type": "normal", "duration_seconds": 30},
        {"type": "normal", "duration_seconds": 30},
    ]


def test_workout_backfill_circuit_ladder_requires_agent_decision(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(store, [("hevy-squat", "Goblet Squat"), ("hevy-push-up", "Push Up")])
    _add_circuit_backfill_item(
        store,
        name="3 Round Circuit",
        info="""
        Goblet Squat
        Push Up
        Round 1: 12 reps
        Round 2: 10 reps
        Round 3: 8 reps
        """,
        comment="3 Rounds",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    report = (bundle_dir / "report.md").read_text(encoding="utf-8")

    circuit_items = plan["items"][2:]
    assert [item["name"] for item in circuit_items] == ["Goblet Squat", "Push Up"]
    assert [item["blockers"] for item in circuit_items] == [
        ["Circuit block requires Agent decision: round_specific_rep_ladder"],
        ["Circuit block requires Agent decision: round_specific_rep_ladder"],
    ]
    assert "BLOCKER: Circuit block requires Agent decision: round_specific_rep_ladder" in report

    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    with pytest.raises(
        WorkoutBackfillApplyError,
        match="Circuit block requires Agent decision: round_specific_rep_ladder",
    ):
        service.write_apply_request(455045484)


def test_workout_backfill_circuit_item_missing_template_writes_required_decision(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_circuit_backfill_item(
        store,
        info="10 Burpees\nPlank 30s",
        comment="3 Rounds",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    decisions = json.loads((bundle_dir / "decisions.json").read_text(encoding="utf-8"))
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))

    assert decisions["circuit_items"] == [
        {
            "source_id": 8106,
            "movement_name": "Burpees",
            "selected_hevy_template_id": None,
            "candidate_template_ids": [],
            "reason": "missing_template",
        },
        {
            "source_id": 8106,
            "movement_name": "Plank",
            "selected_hevy_template_id": None,
            "candidate_template_ids": [],
            "reason": "missing_template",
        },
    ]
    assert validation["blockers"] == [
        "Missing required decision: selected Workout timestamps",
        "Missing required decision: Circuit Workout Item 8106 Burpees template",
        "Missing required decision: Circuit Workout Item 8106 Plank template",
    ]


def test_workout_backfill_circuit_replacement_requires_explicit_decision(  # noqa: PLR0915
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(
        store,
        [
            ("hevy-bike", "Bike"),
            ("hevy-burpees", "Burpees"),
            ("hevy-ski-erg", "Ski Erg"),
        ],
    )
    _add_circuit_backfill_item(
        store,
        info="2 Rounds\n10 Burpees\n15 Bike",
        comment="2 Rounds\nW/o Bike, Ski Erg instead",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    decisions = json.loads((bundle_dir / "decisions.json").read_text(encoding="utf-8"))
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))
    report = (bundle_dir / "report.md").read_text(encoding="utf-8")

    replacement_item = plan["items"][3]
    assert replacement_item["name"] == "Ski Erg"
    assert replacement_item["selected_hevy_template"] is None
    assert replacement_item["replacement_for_movement_name"] == "Bike"
    assert replacement_item["replacement_source_comment"] == "W/o Bike, Ski Erg instead"
    assert replacement_item["circuit_template_candidates"] == ["hevy-ski-erg"]
    assert replacement_item["circuit_decision_reason"] == "replacement_exercise"
    assert replacement_item["blockers"] == [
        "Circuit Workout Item 8106 Bike replacement requires Agent decision: Ski Erg"
    ]
    assert replacement_item["sets"] == [
        {"type": "normal", "reps": 15},
        {"type": "normal", "reps": 15},
    ]
    assert decisions["circuit_items"] == [
        {
            "source_id": 8106,
            "movement_name": "Ski Erg",
            "selected_hevy_template_id": None,
            "candidate_template_ids": ["hevy-ski-erg"],
            "reason": "replacement_exercise",
            "replacement_for_movement_name": "Bike",
            "replacement_source_comment": "W/o Bike, Ski Erg instead",
        }
    ]
    assert validation["blockers"] == [
        "Missing required decision: selected Workout timestamps",
        "Missing required decision: Circuit Workout Item 8106 Ski Erg template",
    ]
    assert [exercise["exercise_template_id"] for exercise in request["workout"]["exercises"]] == [
        "hevy-bench",
        "hevy-row",
        "hevy-burpees",
    ]
    assert "Replacement for generated movement: Bike" in report
    assert "Replacement source comment: W/o Bike, Ski Erg instead" in report

    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    with pytest.raises(
        WorkoutBackfillApplyError,
        match="Missing required decision: Circuit Workout Item 8106 Ski Erg template",
    ):
        service.write_apply_request(455045484)


def test_workout_backfill_circuit_replacement_applies_explicit_decision(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(
        store,
        [
            ("hevy-bike", "Bike"),
            ("hevy-burpees", "Burpees"),
            ("hevy-ski-erg", "Ski Erg"),
        ],
    )
    _add_circuit_backfill_item(
        store,
        info="2 Rounds\n10 Burpees\n15 Bike",
        comment="2 Rounds\nW/o Bike, Ski Erg instead",
    )
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workout": {
                    "id": 455045484,
                    "selected_start_time": "2024-04-10T17:05:00Z",
                    "selected_end_time": "2024-04-10T18:02:00Z",
                },
                "circuit_items": [
                    {
                        "source_id": 8106,
                        "movement_name": "Ski Erg",
                        "selected_hevy_template_id": "hevy-ski-erg",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = _run_backfill_review(tmp_path, 455045484, decisions_path)

    assert exit_code == 0
    bundle_dir = tmp_path / "reports" / "workout-backfill" / "455045484"
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))

    assert validation == {"blockers": [], "warnings": []}
    assert [exercise["exercise_template_id"] for exercise in request["workout"]["exercises"]] == [
        "hevy-bench",
        "hevy-row",
        "hevy-burpees",
        "hevy-ski-erg",
    ]
    assert request["workout"]["exercises"][3]["sets"] == [
        {
            "type": "normal",
            "weight_kg": None,
            "reps": 15,
            "distance_meters": None,
            "duration_seconds": None,
            "rpe": None,
        },
        {
            "type": "normal",
            "weight_kg": None,
            "reps": 15,
            "distance_meters": None,
            "duration_seconds": None,
            "rpe": None,
        },
    ]


def test_workout_backfill_choice_item_missing_template_writes_required_decision(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_backfill_item(
        store,
        info="Cycle, Cross Trainer, Stairmaster or a Combination",
        comment="Cross Trainer 15mins",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    decisions = json.loads((bundle_dir / "decisions.json").read_text(encoding="utf-8"))
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))

    assert plan["blockers"] == [
        "Missing Hevy template mapping for Choice Workout Item 8104: Cross Trainer"
    ]
    assert decisions["choice_items"] == [
        {
            "source_id": 8104,
            "performed_name": "Cross Trainer",
            "selected_hevy_template_id": None,
            "candidate_template_ids": [],
            "reason": "missing_template",
        }
    ]
    assert validation["blockers"] == [
        "Missing required decision: selected Workout timestamps",
        "Missing required decision: Choice Workout Item 8104 Cross Trainer template",
    ]
    assert [exercise["exercise_template_id"] for exercise in request["workout"]["exercises"]] == [
        "hevy-bench",
        "hevy-row",
    ]


def test_workout_backfill_choice_item_ambiguous_template_writes_required_decision(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(
        store,
        [
            ("hevy-cross-trainer-a", "Cross Trainer"),
            ("hevy-cross-trainer-b", "Cross Trainer"),
        ],
    )
    _add_choice_backfill_item(
        store,
        info="Cycle, Cross Trainer, Stairmaster or a Combination",
        comment="Cross Trainer 15mins",
    )

    bundle_dir = _write_backfill_review(db_path, tmp_path)
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    decisions = json.loads((bundle_dir / "decisions.json").read_text(encoding="utf-8"))
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))

    assert plan["blockers"] == [
        "Ambiguous Hevy template mapping for Choice Workout Item 8104: "
        "Cross Trainer (hevy-cross-trainer-a, hevy-cross-trainer-b)"
    ]
    assert decisions["choice_items"] == [
        {
            "source_id": 8104,
            "performed_name": "Cross Trainer",
            "selected_hevy_template_id": None,
            "candidate_template_ids": ["hevy-cross-trainer-a", "hevy-cross-trainer-b"],
            "reason": "ambiguous_template",
        }
    ]
    assert validation["blockers"] == [
        "Missing required decision: selected Workout timestamps",
        "Missing required decision: Choice Workout Item 8104 Cross Trainer template",
    ]


def test_workout_backfill_choice_item_applies_template_decision_to_request(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_backfill_item(
        store,
        info="Cycle, Cross Trainer, Stairmaster or a Combination",
        comment="Cross Trainer 15mins",
    )
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workout": {
                    "id": 455045484,
                    "selected_start_time": "2024-04-10T17:05:00Z",
                    "selected_end_time": "2024-04-10T18:02:00Z",
                },
                "choice_items": [
                    {
                        "source_id": 8104,
                        "performed_name": "Cross Trainer",
                        "selected_hevy_template_id": "hevy-cross-trainer",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = _run_backfill_review(tmp_path, 455045484, decisions_path)

    assert exit_code == 0
    bundle_dir = tmp_path / "reports" / "workout-backfill" / "455045484"
    request = json.loads((bundle_dir / "hevy-workout-request.json").read_text(encoding="utf-8"))
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))

    assert validation == {"blockers": [], "warnings": []}
    assert request["workout"]["exercises"][2]["exercise_template_id"] == "hevy-cross-trainer"
    assert request["workout"]["exercises"][2]["sets"] == [
        {
            "type": "normal",
            "weight_kg": None,
            "reps": None,
            "distance_meters": None,
            "duration_seconds": 900,
            "rpe": None,
        }
    ]


def test_workout_backfill_apply_dry_run_blocks_missing_timestamps(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")

    with pytest.raises(
        WorkoutBackfillApplyError,
        match="Missing required decision: selected Workout timestamps",
    ):
        service.write_apply_request(455045484)


def test_workout_backfill_apply_dry_run_blocks_missing_hevy_template_mapping(
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
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workout": {
                    "id": 455045484,
                    "selected_start_time": "2024-04-10T17:05:00Z",
                    "selected_end_time": "2024-04-10T18:02:00Z",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")

    with pytest.raises(
        WorkoutBackfillApplyError,
        match="Missing Hevy template mapping for performed item: Chest Supported Row",
    ):
        service.write_apply_request(455045484, decisions_path=decisions_path)


def test_workout_backfill_apply_sends_same_hevy_request_as_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workout": {
                    "id": 455045484,
                    "selected_start_time": "2024-04-10T17:05:00Z",
                    "selected_end_time": "2024-04-10T18:02:00Z",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    dry_run = service.write_apply_request(455045484, decisions_path=decisions_path)
    writer = _RecordingWorkoutWriter()

    applied = service.apply(
        455045484,
        workout_writer=writer,
        decisions_path=decisions_path,
    )

    assert len(writer.requests) == 1
    assert writer.requests[0].model_dump() == json.loads(dry_run.request_path.read_text())
    assert applied.request_body.model_dump() == writer.requests[0].model_dump()
    assert "True Coach Workout 455045484" in writer.requests[0].workout.description


def test_workout_backfill_apply_skips_already_linked_tracker_workout(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    with store.unit_of_work() as uow:
        workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert workout is not None
        workout.hevy_app_id = "hevy-existing"
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workout": {
                    "id": 455045484,
                    "selected_start_time": "2024-04-10T17:05:00Z",
                    "selected_end_time": "2024-04-10T18:02:00Z",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    writer = _RecordingWorkoutWriter()

    service.apply(
        455045484,
        workout_writer=writer,
        decisions_path=decisions_path,
    )

    assert writer.requests == []


def test_workout_backfill_apply_links_created_hevy_workout_to_tracker_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    decisions_path = _write_timestamp_decisions(tmp_path)
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    writer = _RecordingWorkoutWriter(
        response=_hevy_workout_response(workout_id="hevy-created-455045484")
    )

    service.apply(
        455045484,
        workout_writer=writer,
        decisions_path=decisions_path,
    )

    with store.unit_of_work() as uow:
        tracker_workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert tracker_workout is not None
        assert tracker_workout.hevy_app_id == "hevy-created-455045484"
        tracker_items = sorted(tracker_workout.workout_items, key=lambda item: item.position)
        assert [item.hevy_app_id for item in tracker_items] == [1, 2]
        assert [
            set_row.hevy_app_id
            for item in tracker_items
            for set_row in sorted(item.sets, key=lambda row: row.index)
        ] == [1, 2, 3, 4, 5]


def test_workout_backfill_apply_persists_synthetic_tracker_items_for_split_circuit(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(store, [("hevy-burpees", "Burpees"), ("hevy-plank", "Plank")])
    _add_circuit_backfill_item(
        store,
        info="2 Rounds\n10 Burpees\nPlank 30s",
        comment="2 min 10 sec\n2 min 15 sec",
    )
    decisions_path = _write_timestamp_decisions(tmp_path)
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    writer = _RecordingWorkoutWriter(
        response=_split_circuit_hevy_workout_response(workout_id="hevy-created-455045484")
    )

    service.apply(
        455045484,
        workout_writer=writer,
        decisions_path=decisions_path,
    )

    with store.unit_of_work() as uow:
        tracker_workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert tracker_workout is not None
        tracker_items = sorted(
            (item for item in tracker_workout.workout_items if item.hevy_app_id is not None),
            key=lambda item: item.hevy_app_id or 0,
        )
        assert [(item.exercise.name, item.hevy_app_id) for item in tracker_items] == [
            ("Bench Press", 1),
            ("Chest Supported Row", 2),
            ("Burpees", 3),
            ("Plank", 4),
        ]
        assert [item.true_coach_id for item in tracker_items] == [8101, 8102, 8106, 8106]
        assert [item.exercise.hevy_app_id for item in tracker_items] == [
            "hevy-bench",
            "hevy-row",
            "hevy-burpees",
            "hevy-plank",
        ]
        assert [
            set_row.hevy_app_id
            for item in tracker_items
            for set_row in sorted(item.sets, key=lambda row: row.index)
        ] == [1, 2, 3, 4, 5, 6, 7, 8, 9]


@pytest.mark.parametrize(
    ("comment", "expected"),
    [
        ("W/o Bike", {"bike": "W/o Bike"}),
        ("2 Rounds w/o Bike", {"bike": "w/o Bike"}),
        ("2 Rounds\nwithout Bike", {"bike": "without Bike"}),
    ],
)
def test_omitted_movement_names_extracts_comment_suffixes(
    comment: str,
    expected: dict[str, str],
) -> None:
    assert _omitted_movement_names(comment) == expected


def test_workout_backfill_apply_does_not_create_synthetic_tracker_item_for_inline_omission(
    tmp_path: Path,
) -> None:
    store = Store(create_engine(f"sqlite:///{tmp_path / 'tracker.sqlite'}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(
        store,
        [
            ("hevy-bike", "Bike"),
            ("hevy-burpees", "Burpees"),
            ("hevy-plank", "Plank"),
        ],
    )
    _add_circuit_backfill_item(
        store,
        info="2 Rounds\n10 Burpees\n15 Bike\nPlank 30s",
        comment="2 Rounds w/o Bike",
    )
    decisions_path = _write_timestamp_decisions(tmp_path)
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    writer = _RecordingWorkoutWriter(
        response=_split_circuit_hevy_workout_response(workout_id="hevy-created-455045484")
    )

    dry_run = service.write_apply_request(455045484, decisions_path=decisions_path)
    plan = json.loads(
        (tmp_path / "reports" / "workout-backfill" / "455045484" / "plan.json").read_text(
            encoding="utf-8"
        )
    )
    service.apply(
        455045484,
        workout_writer=writer,
        decisions_path=decisions_path,
    )

    assert [
        exercise.exercise_template_id for exercise in dry_run.request_body.workout.exercises
    ] == [
        "hevy-bench",
        "hevy-row",
        "hevy-burpees",
        "hevy-plank",
    ]
    bike_item = next(item for item in plan["items"] if item["name"] == "Bike")
    assert bike_item["sets"] == []
    assert bike_item["warnings"] == ["Athlete comment omits Circuit movement: w/o Bike"]
    with store.unit_of_work() as uow:
        tracker_workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert tracker_workout is not None
        synthetic_items = [
            item
            for item in tracker_workout.workout_items
            if item.true_coach_id == 8106 and item.exercise.hevy_app_id is not None
        ]
        assert [(item.exercise.name, item.hevy_app_id) for item in synthetic_items] == [
            ("Burpees", 3),
            ("Plank", 4),
        ]


def test_workout_backfill_apply_repairs_local_links_from_existing_remote_marker(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    decisions_path = _write_timestamp_decisions(tmp_path)
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    writer = _RecordingWorkoutWriter(
        existing_workout=_hevy_workout_response(workout_id="hevy-existing-455045484").workout[0],
    )

    service.apply(
        455045484,
        workout_writer=writer,
        decisions_path=decisions_path,
    )

    assert writer.requests == []
    assert writer.marker_searches == [455045484]
    with store.unit_of_work() as uow:
        tracker_workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert tracker_workout is not None
        assert tracker_workout.hevy_app_id == "hevy-existing-455045484"
        assert [
            item.hevy_app_id
            for item in sorted(tracker_workout.workout_items, key=lambda i: i.position)
        ] == [
            1,
            2,
        ]


def test_workout_backfill_repair_uses_linked_remote_workout_without_creating(  # noqa: PLR0915
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    with store.unit_of_work() as uow:
        workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert workout is not None
        workout.hevy_app_id = "hevy-linked-455045484"
    decisions_path = _write_timestamp_decisions(tmp_path)
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    writer = _RecordingWorkoutWriter(
        existing_workout=_hevy_workout_response(workout_id="hevy-linked-455045484").workout[0],
    )

    result = service.repair_local_links(
        455045484,
        workout_writer=writer,
        decisions_path=decisions_path,
    )

    assert result.action == "repaired_existing_remote"
    assert writer.requests == []
    assert writer.get_workout_requests == ["hevy-linked-455045484"]
    assert writer.marker_searches == []
    with store.unit_of_work() as uow:
        tracker_workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert tracker_workout is not None
        tracker_items = sorted(tracker_workout.workout_items, key=lambda item: item.position)
        assert [item.hevy_app_id for item in tracker_items] == [1, 2]


def test_workout_backfill_repair_reuses_synthetic_tracker_items_for_split_circuit(  # noqa: PLR0915
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    _add_choice_templates(store, [("hevy-burpees", "Burpees"), ("hevy-plank", "Plank")])
    _add_circuit_backfill_item(
        store,
        info="2 Rounds\n10 Burpees\nPlank 30s",
        comment="2 min 10 sec\n2 min 15 sec",
    )
    with store.unit_of_work() as uow:
        workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert workout is not None
        workout.hevy_app_id = "hevy-linked-455045484"
    decisions_path = _write_timestamp_decisions(tmp_path)
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    writer = _RecordingWorkoutWriter(
        existing_workout=_split_circuit_hevy_workout_response(
            workout_id="hevy-linked-455045484"
        ).workout[0],
    )

    service.repair_local_links(
        455045484,
        workout_writer=writer,
        decisions_path=decisions_path,
    )
    service.repair_local_links(
        455045484,
        workout_writer=writer,
        decisions_path=decisions_path,
    )

    with store.unit_of_work() as uow:
        tracker_workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert tracker_workout is not None
        synthetic_items = sorted(
            (
                item
                for item in tracker_workout.workout_items
                if item.true_coach_id == 8106 and item.exercise.hevy_app_id is not None
            ),
            key=lambda item: item.hevy_app_id or 0,
        )
        assert [(item.exercise.name, item.hevy_app_id) for item in synthetic_items] == [
            ("Burpees", 3),
            ("Plank", 4),
        ]
        assert [
            set_row.hevy_app_id
            for item in synthetic_items
            for set_row in sorted(item.sets, key=lambda row: row.index)
        ] == [6, 7, 8, 9]


def test_workout_backfill_apply_writes_recovery_artifact_when_local_linking_fails(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    decisions_path = _write_timestamp_decisions(tmp_path)
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    response = _hevy_workout_response(workout_id="hevy-partial-455045484")
    response.workout[0].exercises = response.workout[0].exercises[:1]
    writer = _RecordingWorkoutWriter(response=response)

    with pytest.raises(
        WorkoutBackfillApplyError,
        match="Could not link all created Hevy rows",
    ):
        service.apply(
            455045484,
            workout_writer=writer,
            decisions_path=decisions_path,
        )

    recovery_path = (
        tmp_path / "reports" / "workout-backfill" / "455045484" / "backfill-recovery.json"
    )
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    assert recovery["true_coach_workout_id"] == 455045484
    assert recovery["remote_hevy_workout_id"] == "hevy-partial-455045484"
    assert recovery["unlinked_tracker_workout_item_ids"] == [2]
    assert recovery["request_path"].endswith("hevy-workout-request.json")


def test_workout_backfill_manual_request_apply_accepts_edited_artifact(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_backfill_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workout": {
                    "id": 455045484,
                    "selected_start_time": "2024-04-10T17:05:00Z",
                    "selected_end_time": "2024-04-10T18:02:00Z",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    dry_run = service.write_apply_request(455045484, decisions_path=decisions_path)
    edited = json.loads(dry_run.request_path.read_text())
    edited["workout"]["title"] = "Edited Upper Backfill"
    edited_path = tmp_path / "edited-hevy-workout-request.json"
    edited_path.write_text(json.dumps(edited) + "\n", encoding="utf-8")
    writer = _RecordingWorkoutWriter()

    result = service.apply_manual_request(
        edited_path,
        workout_id=455045484,
        workout_writer=writer,
    )

    assert len(writer.requests) == 1
    assert writer.requests[0].workout.title == "Edited Upper Backfill"
    assert result.request_body.model_dump() == writer.requests[0].model_dump()


def test_455045484_workout_backfill_fixture_runs_end_to_end(
    tmp_path: Path,
) -> None:
    db_path, store = _new_sqlite_store(tmp_path)
    _seed_backfill_review_workout(store)
    decisions_path = _write_timestamp_decisions(tmp_path)

    discovery_exit_code = _run_backfill_discovery(db_path, tmp_path)
    review_exit_code = _run_backfill_review(tmp_path, 455045484, decisions_path)

    assert discovery_exit_code == 0
    assert review_exit_code == 0
    _assert_discovered_workout_ids(tmp_path, [455045484])

    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    dry_run = service.write_apply_request(455045484, decisions_path=decisions_path)
    _assert_455045484_request(dry_run.request_body.model_dump())

    writer = _RecordingWorkoutWriter(
        response=_hevy_workout_response(workout_id="hevy-created-455045484")
    )
    service.apply(455045484, workout_writer=writer, decisions_path=decisions_path)

    assert len(writer.requests) == 1
    assert writer.marker_searches == [455045484]
    _assert_455045484_local_links(store)


def test_placeholder_only_workout_backfill_is_visible_but_not_applicable(
    tmp_path: Path,
) -> None:
    _, store = _new_sqlite_store(tmp_path)
    _seed_placeholder_only_backfill_workout(store)
    decisions_path = _write_timestamp_decisions(
        tmp_path,
        {
            "id": 455047508,
            "selected_start_time": "2024-04-12T20:00:00Z",
            "selected_end_time": "2024-04-12T23:00:00Z",
        },
    )

    exit_code = _run_backfill_review(tmp_path, 455047508, decisions_path)
    assert exit_code == 0
    _assert_placeholder_only_review(tmp_path)

    service = TrueCoachWorkoutBackfillReviewService(store=store, output_root=tmp_path / "reports")
    with pytest.raises(
        WorkoutBackfillApplyError,
        match="No performed exercise blocks are requestable for Workout backfill",
    ):
        service.write_apply_request(455047508, decisions_path=decisions_path)


def _new_sqlite_store(tmp_path: Path) -> tuple[Path, Store]:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    return db_path, store


def _run_backfill_discovery(db_path: Path, tmp_path: Path) -> int:
    return main(
        [
            "workout-backfill",
            "candidates",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )


def _run_backfill_review(
    tmp_path: Path,
    workout_id: int,
    decisions_path: Path,
) -> int:
    review_exit_code = main(
        [
            "workout-backfill",
            "review",
            "--workout-id",
            str(workout_id),
            "--database-url",
            f"sqlite:///{tmp_path / 'tracker.sqlite'}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )
    if review_exit_code != 0:
        return review_exit_code
    review_dir = tmp_path / "reports" / "workout-backfill" / str(workout_id)
    (review_dir / "decisions.json").write_text(
        decisions_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    request_exit_code = main(
        [
            "workout-backfill",
            "write-request",
            "--review-dir",
            str(review_dir),
            "--force",
        ]
    )
    if request_exit_code == 2:
        return review_exit_code
    return request_exit_code


def _write_requestable_pipeline_decisions(decisions_path: Path) -> None:
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    decisions["workout"]["selected_start_time"] = "2024-04-10T13:00:00+00:00"
    decisions["workout"]["selected_end_time"] = "2024-04-10T14:00:00+00:00"
    decisions_path.write_text(json.dumps(decisions) + "\n", encoding="utf-8")


def _seed_linked_local_hevy_workout(store: Store, *, title: str = "2024-04-10 Upper") -> None:
    with store.unit_of_work() as uow:
        workout = uow.session.query(TrackerWorkout).filter_by(true_coach_id=455045484).one()
        workout.hevy_app_id = "hevy-linked-455045484"
        hevy_workout = HevyAppWorkout(
            id="hevy-linked-455045484",
            title=title,
            description="Backfill from True Coach Workout 455045484",
            start_time=datetime(2024, 4, 10, 13, tzinfo=UTC),
            end_time=datetime(2024, 4, 10, 14, tzinfo=UTC),
        )
        uow.session.add(hevy_workout)
        uow.session.flush()
        bench_item = HevyAppWorkoutItem(
            workout_id=hevy_workout.id,
            index=0,
            name="Bench Press",
            notes="",
            superset_id=0,
            exercise_id="hevy-bench",
        )
        row_item = HevyAppWorkoutItem(
            workout_id=hevy_workout.id,
            index=1,
            name="Chest Supported Row",
            notes="Athlete comment: smooth reps",
            superset_id=0,
            exercise_id="hevy-row",
        )
        uow.session.add(bench_item)
        uow.session.add(row_item)
        uow.session.flush()
        for index in range(3):
            uow.session.add(
                HevyAppSets(
                    workout_item_id=bench_item.id,
                    index=index,
                    type="normal",
                    weight_kg=80.0,
                    reps=8,
                )
            )
        for index in range(2):
            uow.session.add(
                HevyAppSets(
                    workout_item_id=row_item.id,
                    index=index,
                    type="normal",
                    weight_kg=55.0,
                    reps=10,
                )
            )


def _assert_discovered_workout_ids(tmp_path: Path, expected_ids: list[int]) -> None:
    candidates_path = tmp_path / "reports" / "workout-backfill" / "candidates" / "candidates.json"
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    assert [candidate["true_coach_id"] for candidate in candidates] == expected_ids


def _assert_455045484_request(request: dict) -> None:
    assert request["workout"]["description"] == "Backfill from True Coach Workout 455045484"
    assert request["workout"]["exercises"][0]["notes"] is None
    assert request["workout"]["exercises"][0]["sets"] == [
        _structured_set(weight_kg=80.0, reps=8),
        _structured_set(weight_kg=80.0, reps=8),
        _structured_set(weight_kg=80.0, reps=8),
    ]
    assert request["workout"]["exercises"][1]["notes"] == "Athlete comment: smooth reps"


def _structured_set(*, weight_kg: float, reps: int) -> dict[str, int | float | str | None]:
    return {
        "type": "normal",
        "weight_kg": weight_kg,
        "reps": reps,
        "distance_meters": None,
        "duration_seconds": None,
        "rpe": None,
    }


def _assert_455045484_local_links(store: Store) -> None:
    with store.unit_of_work() as uow:
        tracker_workout = uow.tracker.get_workout(true_coach_id=455045484)
        assert tracker_workout is not None
        assert tracker_workout.hevy_app_id == "hevy-created-455045484"
        tracker_items = sorted(tracker_workout.workout_items, key=lambda item: item.position)
        assert [item.hevy_app_id for item in tracker_items] == [1, 2]
        assert [
            set_row.hevy_app_id
            for item in tracker_items
            for set_row in sorted(item.sets, key=lambda row: row.index)
        ] == [1, 2, 3, 4, 5]


def _assert_placeholder_only_review(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "reports" / "workout-backfill" / "455047508"
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    report = (bundle_dir / "report.md").read_text(encoding="utf-8")
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))

    assert plan["blockers"] == []
    assert plan["warnings"] == [
        "Placeholder rest item has no structured Sets rows; omitted from draft request."
    ]
    assert plan["items"] == [
        {
            "source_id": 8201,
            "tracker_workout_item_id": 1,
            "position": 1,
            "superset_id": None,
            "name": "Wedding Dancing",
            "info": "placeholder",
            "comment": "",
            "selected_hevy_template": None,
            "sets": [],
            "notes": "Coach prescription: placeholder",
            "warnings": [
                "Placeholder rest item has no structured Sets rows; omitted from draft request."
            ],
            "blockers": [],
        }
    ]
    assert not (bundle_dir / "hevy-workout-request.json").exists()
    assert validation == {
        "blockers": ["Missing required decision: selected Workout timestamps"],
        "warnings": [],
    }
    assert "WARNING: Placeholder rest item has no structured Sets rows" in report


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
                comment=item.get("comment") or "",
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


def _add_choice_templates(store: Store, templates: list[tuple[str, str]]) -> None:
    with store.unit_of_work() as uow:
        for template_id, name in templates:
            uow.session.add(
                HevyAppExercise(
                    id=template_id,
                    name=name,
                    type="duration",
                    equipment="machine",
                    default=False,
                )
            )


def _add_choice_backfill_item(  # noqa: PLR0913
    store: Store,
    *,
    info: str,
    comment: str,
    name: str = "Conditioning Choice",
) -> None:
    with store.unit_of_work() as uow:
        workout = uow.true_coach.get_workout(id=455045484).tracker
        assert workout is not None
        exercise = Exercise(name="Choice Conditioning", hevy_app_id=None)
        uow.session.add(exercise)
        uow.session.add(
            TrueCoachWorkoutItem(
                id=8104,
                workout_id=455045484,
                name=name,
                info=info,
                comment=comment,
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
                true_coach_id=8104,
            )
        )


def _add_circuit_backfill_item(  # noqa: PLR0913
    store: Store,
    *,
    name: str = "Conditioning Circuit",
    info: str,
    comment: str,
    state: str = "completed",
) -> None:
    with store.unit_of_work() as uow:
        workout = uow.true_coach.get_workout(id=455045484).tracker
        assert workout is not None
        exercise = Exercise(name="Circuit", hevy_app_id=None)
        uow.session.add(exercise)
        uow.session.add(
            TrueCoachWorkoutItem(
                id=8106,
                workout_id=455045484,
                name=name,
                info=info,
                comment=comment,
                is_circuit=True,
                state=state,
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
                true_coach_id=8106,
            )
        )


def _add_distance_backfill_item(store: Store) -> None:
    with store.unit_of_work() as uow:
        workout = uow.true_coach.get_workout(id=455045484).tracker
        assert workout is not None
        template = HevyAppExercise(
            id="hevy-rower",
            name="Rowing Machine",
            type="distance_duration",
            equipment="machine",
            default=False,
        )
        exercise = Exercise(name="Row", hevy_app_id="hevy-rower")
        uow.session.add(template)
        uow.session.add(exercise)
        uow.session.add(
            TrueCoachWorkoutItem(
                id=8105,
                workout_id=455045484,
                name="Row",
                info="3 x 200m",
                comment="",
                is_circuit=False,
                state="completed",
                position=3,
                exercise_id=None,
                assessment_id=None,
            )
        )
        uow.session.flush()
        tracker_item = TrackerWorkoutItem(
            workout_id=workout.id,
            position=3,
            exercise_id=exercise.id,
            true_coach_id=8105,
        )
        uow.session.add(tracker_item)
        uow.session.flush()
        for index in range(3):
            uow.session.add(
                Sets(
                    workout_item_id=tracker_item.id,
                    index=index,
                    type="normal",
                    distance_meters=200,
                    duration_seconds=60,
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
                short_description=(
                    '<p class="name-and-info">A1) Bench Press<br/>A2) Chest Supported Row</p>'
                ),
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


def _seed_placeholder_only_backfill_workout(store: Store) -> None:
    with store.unit_of_work() as uow:
        placeholder = Exercise(name="Wedding Dancing", hevy_app_id=None)
        uow.session.add(placeholder)
        due = datetime(2024, 4, 12, tzinfo=UTC)
        uow.session.add(
            TrueCoachWorkout(
                id=455047508,
                title="Wedding Dancing",
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
        )
        tracker_workout = TrackerWorkout(
            title="Wedding Dancing",
            description="",
            true_coach_id=455047508,
        )
        uow.session.add(tracker_workout)
        uow.session.flush()
        uow.session.add(
            TrackerWorkoutItem(
                workout_id=tracker_workout.id,
                position=1,
                exercise_id=placeholder.id,
                true_coach_id=8201,
            )
        )


class _RecordingWorkoutWriter:
    def __init__(
        self,
        response: PostWorkoutsResponse | None = None,
        existing_workout: HevyWorkout | None = None,
    ) -> None:
        self.requests: list[PostWorkoutsRequestBody] = []
        self.response = response
        self.existing_workout = existing_workout
        self.marker_searches: list[int] = []
        self.get_workout_requests: list[str] = []

    def create_workout(self, workout: PostWorkoutsRequestBody) -> PostWorkoutsResponse | None:
        self.requests.append(workout)
        return self.response

    def find_workout_by_true_coach_id(self, workout_id: int) -> HevyWorkout | None:
        self.marker_searches.append(workout_id)
        return self.existing_workout

    def get_workout(self, workout_id: str) -> HevyWorkout | None:
        self.get_workout_requests.append(workout_id)
        if self.existing_workout and self.existing_workout.id == workout_id:
            return self.existing_workout
        return None


class _FakeHevyWorkoutClient:
    def __init__(
        self,
        response: PostWorkoutsResponse | None = None,
        existing_workout: HevyWorkout | None = None,
    ) -> None:
        self.workouts = _FakeHevyWorkouts(response, existing_workout)


class _FakeHevyWorkouts:
    def __init__(
        self,
        response: PostWorkoutsResponse | None,
        existing_workout: HevyWorkout | None,
    ) -> None:
        self.created_requests: list[PostWorkoutsRequestBody] = []
        self.response = response
        self.existing_workout = existing_workout

    def create(self, workout: PostWorkoutsRequestBody) -> PostWorkoutsResponse | None:
        self.created_requests.append(workout)
        return self.response

    def get_workout(self, workout_id: str) -> HevyWorkout | None:
        if self.existing_workout and self.existing_workout.id == workout_id:
            return self.existing_workout
        return None

    def get(self, *, page: int, per_page: int) -> object | None:
        if page != 1 or self.existing_workout is None:
            return None
        return type(
            "WorkoutPage",
            (),
            {"workouts": [self.existing_workout], "page_count": 1},
        )()


def _write_timestamp_decisions(
    tmp_path: Path,
    workout: dict[str, int | str] | None = None,
) -> Path:
    if workout is None:
        workout = {
            "id": 455045484,
            "selected_start_time": "2024-04-10T17:05:00Z",
            "selected_end_time": "2024-04-10T18:02:00Z",
        }
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workout": workout,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return decisions_path


def _hevy_workout_response(workout_id: str) -> PostWorkoutsResponse:
    return PostWorkoutsResponse(
        workout=[
            HevyWorkout(
                id=workout_id,
                title="2024-04-10 Upper",
                description="Backfill from True Coach Workout 455045484",
                start_time="2024-04-10T17:05:00Z",
                end_time="2024-04-10T18:02:00Z",
                created_at="2024-04-10T18:03:00Z",
                updated_at="2024-04-10T18:03:00Z",
                exercises=[
                    HevyWorkoutExercise(
                        index=0,
                        title="Bench Press",
                        notes="",
                        exercise_template_id="hevy-bench",
                        superset_id=None,
                        sets=[
                            HevySet(index=0, type="normal", weight_kg=80.0, reps=8),
                            HevySet(index=1, type="normal", weight_kg=80.0, reps=8),
                            HevySet(index=2, type="normal", weight_kg=80.0, reps=8),
                        ],
                    ),
                    HevyWorkoutExercise(
                        index=1,
                        title="Chest Supported Row",
                        notes="Athlete comment: smooth reps",
                        exercise_template_id="hevy-row",
                        superset_id=None,
                        sets=[
                            HevySet(index=0, type="normal", weight_kg=55.0, reps=10),
                            HevySet(index=1, type="normal", weight_kg=55.0, reps=10),
                        ],
                    ),
                ],
            )
        ]
    )


def _split_circuit_hevy_workout_response(workout_id: str) -> PostWorkoutsResponse:
    response = _hevy_workout_response(workout_id)
    response.workout[0].exercises.extend(
        [
            HevyWorkoutExercise(
                index=2,
                title="Burpees",
                notes=(
                    "Circuit source: 2 Rounds\n10 Burpees\nPlank 30s\n"
                    "Movement target: 10\nCompleted rounds: 2\n"
                    "Completed round times: 2 min 10 sec; 2 min 15 sec"
                ),
                exercise_template_id="hevy-burpees",
                superset_id=1,
                sets=[
                    HevySet(index=0, type="normal", reps=10),
                    HevySet(index=1, type="normal", reps=10),
                ],
            ),
            HevyWorkoutExercise(
                index=3,
                title="Plank",
                notes=(
                    "Circuit source: 2 Rounds\n10 Burpees\nPlank 30s\n"
                    "Movement target: 30s\nCompleted rounds: 2\n"
                    "Completed round times: 2 min 10 sec; 2 min 15 sec"
                ),
                exercise_template_id="hevy-plank",
                superset_id=1,
                sets=[
                    HevySet(index=0, type="normal", duration_seconds=30),
                    HevySet(index=1, type="normal", duration_seconds=30),
                ],
            ),
        ]
    )
    return response


def _write_backfill_review(db_path: Path, tmp_path: Path) -> Path:
    store = Store(create_engine(f"sqlite:///{db_path}"))
    service = TrueCoachWorkoutBackfillReviewService(
        store=store,
        output_root=tmp_path / "reports",
    )
    return service.write_review(455045484).directory


def _seed_apple_health_evidence(
    store: Store,
    *,
    workouts: list[tuple[str, str, str]],
    heart_rates: list[tuple[str, float]],
) -> None:
    with store.unit_of_work() as uow:
        workout_type_ids: dict[str, int] = {}
        for name, start, end in workouts:
            workout_type = workout_type_ids.get(name)
            if workout_type is None:
                row = AppleHealthWorkoutType(name=name)
                uow.session.add(row)
                uow.session.flush()
                workout_type = row.id
                workout_type_ids[name] = workout_type
            uow.session.add(
                AppleHealthWorkout(
                    workout_type_id=workout_type,
                    start_date=datetime.fromisoformat(start),
                    end_date=datetime.fromisoformat(end),
                )
            )
        if heart_rates:
            heart_rate_type = AppleHealthDataType(name="Heart Rate", unit="count/min")
            uow.session.add(heart_rate_type)
            uow.session.flush()
            for timestamp, value in heart_rates:
                uow.session.add(
                    AppleHealthDataRecord(
                        data_type_id=heart_rate_type.id,
                        timestamp=datetime.fromisoformat(timestamp),
                        value=value,
                    )
                )
