from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from fitness_tracker.apis.hevy_app.types import PostWorkoutsRequestBody
from fitness_tracker.cli import main
from fitness_tracker.database import Store
from fitness_tracker.database.models.apple_health import (
    AppleHealthDataRecord,
    AppleHealthDataType,
    AppleHealthWorkout,
    AppleHealthWorkoutType,
)
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.tracker import (
    Exercise,
    Sets,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachWorkoutItem
from fitness_tracker.sync_review.true_coach_workout_backfill import (
    WorkoutBackfillApplyError,
    TrueCoachWorkoutBackfillReviewService,
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
    decisions = json.loads((bundle_dir / "backfill-decisions.json").read_text(encoding="utf-8"))
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
            "--decisions",
            str(decisions_path),
        ]
    )

    assert exit_code == 0
    bundle_dir = tmp_path / "reports" / "sync-review" / "truecoach-workout-backfill" / "455045484"
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
        "Athlete comment: Cycle 20mins, 1840 steps, 250 calories"
    )
    assert request["workout"]["exercises"][3]["notes"] == (
        "Athlete comment: Stairmaster 10mins, 1840 steps, 250 calories"
    )


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
    decisions = json.loads((bundle_dir / "backfill-decisions.json").read_text(encoding="utf-8"))
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
    decisions = json.loads((bundle_dir / "backfill-decisions.json").read_text(encoding="utf-8"))
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
            "--decisions",
            str(decisions_path),
        ]
    )

    assert exit_code == 0
    bundle_dir = tmp_path / "reports" / "sync-review" / "truecoach-workout-backfill" / "455045484"
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


def _add_choice_backfill_item(store: Store, *, info: str, comment: str) -> None:
    with store.unit_of_work() as uow:
        workout = uow.true_coach.get_workout(id=455045484).tracker
        assert workout is not None
        exercise = Exercise(name="Choice Conditioning", hevy_app_id=None)
        uow.session.add(exercise)
        uow.session.add(
            TrueCoachWorkoutItem(
                id=8104,
                workout_id=455045484,
                name="Conditioning Choice",
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


class _RecordingWorkoutWriter:
    def __init__(self) -> None:
        self.requests: list[PostWorkoutsRequestBody] = []

    def create_workout(self, workout: PostWorkoutsRequestBody) -> None:
        self.requests.append(workout)


def _write_backfill_review(db_path: Path, tmp_path: Path) -> Path:
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
    return tmp_path / "reports" / "sync-review" / "truecoach-workout-backfill" / "455045484"


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
