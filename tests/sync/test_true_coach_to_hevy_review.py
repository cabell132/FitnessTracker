from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from fitness_tracker.cli import main
from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestBody
from fitness_tracker.database import Store
from fitness_tracker.database.models.hevy_app import (
    HevyAppExercise,
    HevyAppSets,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.models.tracker import Exercise as TrackerExercise
from fitness_tracker.database.models.true_coach import (
    TrueCoachExercise,
    TrueCoachWorkout,
    TrueCoachWorkoutItem,
)
from fitness_tracker.sync_review import TrueCoachToHevyReviewService
from fitness_tracker.sync_review.true_coach_to_hevy import SyncApplyError


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
    assert "## Agent Next Actions" in report
    assert "Blocking actions:" in report
    assert (
        '- Create required Hevy template "Single-Leg Isometric Calf Raise" '
        "(type: duration; equipment: bodyweight; muscle group: calves; other muscles: none) "
        "for True Coach Workout Item 1003."
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
    assert (
        '- Resolve ambiguous Hevy template "Isometric Seated Knee Extension" '
        "for True Coach Workout Item 1004; matching template IDs: "
        "hevy-knee-iso-a, hevy-knee-iso-b."
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
    assert item["proposed_sets"] == []
    _assert_mixed_knee_extension_blocks(item)
    assert item["blockers"] == ["Missing required Hevy template: Isometric Seated Knee Extension"]


def test_sync_review_enriches_weight_reps_loads_from_recent_matching_history(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_workout(store)
    _seed_bench_history(store)

    report, plan = _write_sync_review(tmp_path, db_path, workout_id=42)

    assert "- type: normal; weight_kg: 80.0; reps: 12" in report

    bench_item = plan["items"][0]
    assert bench_item["proposed_sets"] == [
        {
            "type": "normal",
            "weight_kg": 80.0,
            "reps": 12,
            "_provenance": {"weight_kg": "athlete_history"},
        },
        {
            "type": "normal",
            "weight_kg": 80.0,
            "reps": 12,
            "_provenance": {"weight_kg": "athlete_history"},
        },
        {
            "type": "normal",
            "weight_kg": 80.0,
            "reps": 12,
            "_provenance": {"weight_kg": "athlete_history"},
        },
    ]


def test_sync_review_does_not_override_explicit_coach_loads(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_workout(store)
    _seed_bench_history(store)
    with store.unit_of_work() as uow:
        item = uow.true_coach.get_workout_item(id=1001)
        assert item is not None
        item.info = "3 x 12 @ 90kg"

    _, plan = _write_sync_review(tmp_path, db_path, workout_id=42)

    assert plan["items"][0]["proposed_sets"] == [
        {"type": "normal", "weight_kg": 90.0, "reps": 12},
        {"type": "normal", "weight_kg": 90.0, "reps": 12},
        {"type": "normal", "weight_kg": 90.0, "reps": 12},
    ]


def test_sync_review_enriches_dropsets_from_matching_dropset_history(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_workout(store)
    with store.unit_of_work() as uow:
        item = uow.true_coach.get_workout_item(id=1001)
        assert item is not None
        item.info = "2 x 10+10"
    _seed_bench_dropset_history(store)

    _, plan = _write_sync_review(tmp_path, db_path, workout_id=42)

    assert plan["items"][0]["proposed_sets"] == [
        {
            "type": "normal",
            "weight_kg": 100.0,
            "reps": 10,
            "_provenance": {"weight_kg": "athlete_history"},
        },
        {
            "type": "dropset",
            "weight_kg": 82.5,
            "reps": 10,
            "_provenance": {"weight_kg": "athlete_history"},
        },
        {
            "type": "normal",
            "weight_kg": 100.0,
            "reps": 10,
            "_provenance": {"weight_kg": "athlete_history"},
        },
        {
            "type": "dropset",
            "weight_kg": 80.0,
            "reps": 10,
            "_provenance": {"weight_kg": "athlete_history"},
        },
    ]


def test_sync_review_calculates_conservative_dropset_load_when_history_is_missing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_workout(store)
    with store.unit_of_work() as uow:
        item = uow.true_coach.get_workout_item(id=1001)
        assert item is not None
        item.info = "1 x 10+10"
    _seed_bench_normal_history(store, reps=10, weight_kg=100.0)

    _, plan = _write_sync_review(tmp_path, db_path, workout_id=42)

    assert plan["items"][0]["proposed_sets"] == [
        {
            "type": "normal",
            "weight_kg": 100.0,
            "reps": 10,
            "_provenance": {"weight_kg": "athlete_history"},
        },
        {
            "type": "dropset",
            "weight_kg": 80.0,
            "reps": 10,
            "_provenance": {"weight_kg": "calculated_dropset"},
        },
    ]


def test_sync_review_treats_missing_history_as_warning_not_blocker(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_workout(store)

    _, plan = _write_sync_review(tmp_path, db_path, workout_id=42)

    bench_item = plan["items"][0]
    assert bench_item["warnings"] == ["No matching Athlete history load found."]
    assert bench_item["blockers"] == []


def test_sync_review_enriches_distance_loads_from_recent_matching_history(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_sled_workout(store)
    _seed_sled_history(store)

    _, plan = _write_sync_review(tmp_path, db_path, workout_id=48)

    item = plan["items"][0]
    assert item["warnings"] == []
    assert item["proposed_sets"] == [
        {
            "type": "normal",
            "weight_kg": 120.0,
            "distance_meters": 10,
            "_provenance": {"weight_kg": "athlete_history"},
        },
        {
            "type": "normal",
            "weight_kg": 120.0,
            "distance_meters": 10,
            "_provenance": {"weight_kg": "athlete_history"},
        },
    ]


def test_sync_review_agent_next_actions_include_parser_gap_source_text(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_parser_gap_workout(store)

    report, plan = _write_sync_review(tmp_path, db_path, workout_id=46)

    assert "## Agent Next Actions" in report
    assert "No blocking next actions." in report
    assert "Warning actions:" in report
    assert (
        "- Add a deterministic set parser fixture or override for True Coach Workout Item 1006 "
        '"Tempo Press" with info "tempo eccentric clusters to technical failure" '
        'and comment "coach wants controlled eccentrics".'
    ) in report
    assert plan["items"][0]["warnings"] == ["No deterministic set parser result found."]


def test_sync_review_agent_next_actions_report_clean_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_clean_plan_workout(store)

    report, plan = _write_sync_review(tmp_path, db_path, workout_id=47)

    assert "## Agent Next Actions" in report
    assert "No blocking next actions." in report
    assert "Blocking actions:" not in report
    assert "Warning actions:" not in report
    assert plan["items"][0]["warnings"] == []
    assert plan["items"][0]["blockers"] == []


def test_sync_review_plan_includes_parsed_circuit_block_context(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_circuit_block_workout(store)

    _, plan = _write_sync_review(tmp_path, db_path, workout_id=51)

    item = plan["items"][0]
    assert item["parsed_circuit_block"] == {
        "kind": "amrap",
        "round_count": None,
        "amrap_time_cap_seconds": 600,
        "movements": [
            {"name": "Bike", "target": "500m", "source_text": "Bike 500m"},
            {"name": "Burpees", "target": "10", "source_text": "10 Burpees"},
        ],
        "rests": [{"source_text": "60s rest", "durations_seconds": [60]}],
        "metadata_lines": [],
        "requires_agent_decision": False,
        "agent_decision_reason": None,
    }
    assert [block["block_kind"] for block in item["planned_blocks"]] == [
        "amrap_movement",
        "amrap_movement",
    ]
    assert [block["selected_hevy_template"] for block in item["planned_blocks"]] == [None, None]
    assert item["blockers"] == [
        "Missing required Hevy exercise mapping: Bike",
        "Missing required Hevy exercise mapping: Burpees",
    ]


def test_sync_review_splits_resolved_amrap_movements_into_planned_blocks(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_circuit_block_workout(store)
    _seed_circuit_movement_templates(store)

    report, plan = _write_sync_review(tmp_path, db_path, workout_id=51)

    assert report.index("Block 1: AMRAP movement") < report.index("Block 2: AMRAP movement")
    assert "Movement: Bike" in report
    assert "Movement target: 500m" in report
    assert "Movement: Burpees" in report
    assert "Blockers: none" in report

    item = plan["items"][0]
    _assert_resolved_amrap_movement_blocks(item)


def test_sync_review_resolves_circuit_movements_with_template_overrides(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_circuit_template_override_workout(store)

    _, plan = _write_sync_review(tmp_path, db_path, workout_id=54)

    item = plan["items"][0]
    blocks = item["planned_blocks"]
    assert blocks[0]["movement_name"] == "Bodyweight Calf Raise"
    assert blocks[0]["selected_hevy_template"]["id"] == "hevy-single-leg-calf-iso"
    assert blocks[0]["required_hevy_templates"] == [
        {
            "title": "Single-Leg Isometric Calf Raise",
            "expected_type": "duration",
            "equipment_category": "bodyweight",
            "muscle_group": "calves",
            "other_muscles": [],
            "status": "existing",
            "source_workout_item_ids": [1013],
            "matching_template_ids": ["hevy-single-leg-calf-iso"],
        }
    ]
    assert blocks[0]["proposed_sets"] == [{"type": "normal", "duration_seconds": 20}]
    assert blocks[0]["blockers"] == []
    assert blocks[1]["selected_hevy_template"]["id"] == "hevy-push-up"
    assert item["blockers"] == []


def test_sync_apply_blocks_circuit_movement_placeholder_templates(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_placeholder_circuit_movement_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    _, plan = _write_sync_review(tmp_path, db_path, workout_id=55)

    blocks = plan["items"][0]["planned_blocks"]
    assert blocks[0]["selected_hevy_template"] is None
    assert blocks[0]["blockers"] == ["Missing required Hevy exercise mapping: Burpees"]
    assert blocks[1]["selected_hevy_template"]["id"] == "hevy-bike"
    with pytest.raises(
        SyncApplyError,
        match="Missing required Hevy exercise mapping: Burpees",
    ):
        service.write_apply_request(55)


def test_sync_apply_keeps_single_movement_circuit_as_one_routine_exercise(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_single_movement_circuit_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    result = service.write_apply_request(56)

    item = json.loads(result.review_bundle.plan_path.read_text())["items"][0]
    assert item["parsed_circuit_block"] is None
    assert item["planned_blocks"] == []
    exercises = result.request_body.model_dump()["routine"]["exercises"]
    assert len(exercises) == 1
    assert exercises[0]["exercise_template_id"] == "hevy-push-up"
    assert exercises[0]["sets"] == [
        {
            "weight_kg": None,
            "reps": 10,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": 10,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": 10,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
    ]


def test_sync_apply_builds_hevy_request_for_resolved_round_circuit(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_round_circuit_request_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    result = service.write_apply_request(57)

    exercises = result.request_body.model_dump()["routine"]["exercises"]
    assert [exercise["exercise_template_id"] for exercise in exercises] == [
        "hevy-burpees",
        "hevy-plank",
    ]
    assert [exercise["superset_id"] for exercise in exercises] == [0, 0]
    assert [exercise["rest_seconds"] for exercise in exercises] == [15, 60]
    assert exercises[0]["sets"] == [
        {
            "weight_kg": None,
            "reps": 10,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": 10,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": 10,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
    ]
    assert exercises[1]["sets"] == [
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": None,
            "duration_seconds": 30,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": None,
            "duration_seconds": 30,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": None,
            "duration_seconds": 30,
            "type": "normal",
        },
    ]


def test_sync_apply_builds_hevy_request_for_resolved_amrap(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_circuit_block_workout(store)
    _seed_circuit_movement_templates(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    result = service.write_apply_request(51)

    exercises = result.request_body.model_dump()["routine"]["exercises"]
    assert [exercise["exercise_template_id"] for exercise in exercises] == [
        "hevy-bike",
        "hevy-burpees",
    ]
    assert [exercise["superset_id"] for exercise in exercises] == [0, 0]
    assert [len(exercise["sets"]) for exercise in exercises] == [5, 5]
    assert exercises[0]["sets"] == [
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": 500,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": 500,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": 500,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": 500,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": 500,
            "duration_seconds": None,
            "type": "normal",
        },
    ]
    assert exercises[1]["sets"][0] == {
        "weight_kg": None,
        "reps": 10,
        "distance_meters": None,
        "duration_seconds": None,
        "type": "normal",
    }
    assert [exercise["rest_seconds"] for exercise in exercises] == [0, 60]


def test_sync_apply_allows_notes_only_generated_circuit_exercise(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_notes_only_circuit_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    result = service.write_apply_request(59)
    plan = json.loads(result.review_bundle.plan_path.read_text(encoding="utf-8"))
    report = result.review_bundle.report_path.read_text(encoding="utf-8")
    exercises = result.request_body.model_dump()["routine"]["exercises"]

    bike_block = plan["items"][0]["planned_blocks"][0]
    assert bike_block["movement_name"] == "Bike"
    assert bike_block["movement_target"] == "15 cals"
    assert bike_block["notes_only"] is True
    assert bike_block["proposed_sets"] == []
    assert bike_block["blockers"] == []
    assert "Notes-only: yes" in report
    assert exercises[0]["exercise_template_id"] == "hevy-bike"
    assert exercises[0]["sets"] == []
    assert "Movement target: 15 cals" in exercises[0]["notes"]
    assert exercises[1]["sets"] == [
        {
            "weight_kg": None,
            "reps": 10,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        }
    ]


def test_sync_apply_assigns_circuit_superset_ids_around_existing_groups(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_superset_and_standalone_circuit_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    result = service.write_apply_request(58)

    exercises = result.request_body.model_dump()["routine"]["exercises"]
    assert [exercise["exercise_template_id"] for exercise in exercises] == [
        "hevy-push-up",
        "hevy-burpees",
        "hevy-plank",
        "hevy-bike",
        "hevy-burpees",
    ]
    assert [exercise["superset_id"] for exercise in exercises] == [0, 0, 0, 1, 1]
    assert [exercise["rest_seconds"] for exercise in exercises] == [0, 0, 30, 0, 0]


def test_sync_review_blocks_circuit_ladder_planned_blocks_for_agent_decision(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_round_ladder_circuit_workout(store)

    report, plan = _write_sync_review(tmp_path, db_path, workout_id=53)

    assert "Block 1: Circuit movement" in report
    assert "Movement: Goblet Squat" in report
    assert "BLOCKER: Circuit block requires Agent decision: round_specific_rep_ladder" in report

    item = plan["items"][0]
    assert [block["block_kind"] for block in item["planned_blocks"]] == [
        "circuit_movement",
        "circuit_movement",
    ]
    assert item["blockers"] == [
        "Circuit block requires Agent decision: round_specific_rep_ladder",
        "Circuit block requires Agent decision: round_specific_rep_ladder",
    ]
    assert [block["blockers"] for block in item["planned_blocks"]] == [
        ["Circuit block requires Agent decision: round_specific_rep_ladder"],
        ["Circuit block requires Agent decision: round_specific_rep_ladder"],
    ]

    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")
    with pytest.raises(
        SyncApplyError,
        match="Circuit block requires Agent decision: round_specific_rep_ladder",
    ):
        service.write_apply_request(53)


def test_sync_apply_dry_run_writes_hevy_request_for_clean_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_clean_plan_workout(store)

    reports_dir = tmp_path / "reports"
    exit_code = main(
        [
            "sync-apply",
            "truecoach-to-hevy",
            "--workout-id",
            "47",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(reports_dir),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    request_path = reports_dir / "sync-review" / "truecoach-to-hevy" / "47" / "hevy-request.json"
    assert json.loads(request_path.read_text()) == {
        "routine": {
            "title": "17 May 2026\nClean Plan\n47",
            "folder_id": None,
            "notes": "TrueCoachWorkoutId: 47\nRoutineBatch: truecoach-to-hevy",
            "exercises": [
                {
                    "exercise_template_id": "hevy-push-up",
                    "superset_id": None,
                    "notes": "3 x 12",
                    "rest_seconds": 0,
                    "sets": [
                        {
                            "weight_kg": None,
                            "reps": 12,
                            "distance_meters": None,
                            "duration_seconds": None,
                            "type": "normal",
                        },
                        {
                            "weight_kg": None,
                            "reps": 12,
                            "distance_meters": None,
                            "duration_seconds": None,
                            "type": "normal",
                        },
                        {
                            "weight_kg": None,
                            "reps": 12,
                            "distance_meters": None,
                            "duration_seconds": None,
                            "type": "normal",
                        },
                    ],
                }
            ],
        }
    }


def test_sync_apply_sends_same_hevy_request_as_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_clean_plan_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")
    dry_run = service.write_apply_request(47)
    writer = _RecordingRoutineWriter()

    applied = service.apply(47, routine_writer=writer)

    assert len(writer.requests) == 1
    assert writer.requests[0].model_dump() == json.loads(dry_run.request_path.read_text())
    assert applied.request_body.model_dump() == writer.requests[0].model_dump()


def test_sync_apply_preserves_true_coach_superset_groups(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_superset_plan_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    result = service.write_apply_request(52)

    exercises = result.request_body.model_dump()["routine"]["exercises"]
    assert [exercise["superset_id"] for exercise in exercises] == [0, 0, 1, 1, None]


def test_sync_apply_blocks_missing_required_exercise_mapping(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    with pytest.raises(
        SyncApplyError,
        match="Missing required Hevy exercise mapping: Mystery Carry",
    ):
        service.write_apply_request(42)


def test_sync_apply_blocks_missing_required_hevy_template(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_template_override_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    with pytest.raises(
        SyncApplyError,
        match="Missing required Hevy template: Single-Leg Isometric Calf Raise",
    ):
        service.write_apply_request(43)


def test_sync_apply_blocks_ambiguous_required_hevy_template(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_template_override_workout(store)
    _seed_ambiguous_knee_extension_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    with pytest.raises(
        SyncApplyError,
        match="Ambiguous required Hevy template: Isometric Seated Knee Extension",
    ):
        service.write_apply_request(44)


def test_sync_apply_allows_missing_history_enrichment_warning(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_clean_weight_plan_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    result = service.write_apply_request(48)

    request = result.request_body.model_dump()
    assert request["routine"]["exercises"][0]["exercise_template_id"] == "hevy-row"
    assert request["routine"]["exercises"][0]["sets"] == [
        {
            "weight_kg": None,
            "reps": 10,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": 10,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
    ]


def test_sync_apply_uses_first_duration_set_as_rest_timer(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_clean_duration_plan_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    result = service.write_apply_request(51)

    exercise = result.request_body.model_dump()["routine"]["exercises"][0]
    assert exercise["rest_seconds"] == 30
    assert exercise["sets"] == [
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": None,
            "duration_seconds": 30,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": None,
            "duration_seconds": 45,
            "type": "normal",
        },
    ]


def test_sync_apply_does_not_use_cardio_machine_duration_as_rest_timer(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_cardio_duration_plan_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    result = service.write_apply_request(59)

    exercise = result.request_body.model_dump()["routine"]["exercises"][0]
    assert exercise["rest_seconds"] == 0
    assert exercise["sets"] == [
        {
            "weight_kg": None,
            "reps": None,
            "distance_meters": None,
            "duration_seconds": 30,
            "type": "normal",
        }
    ]


def test_sync_apply_blocks_unsplit_required_mixed_mode_item(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_unsplit_mixed_mode_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    with pytest.raises(
        SyncApplyError,
        match="Unsplit required mixed-mode item: Seated Knee Extension",
    ):
        service.write_apply_request(49)


def test_sync_apply_blocks_invalid_empty_set_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_parser_gap_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    with pytest.raises(SyncApplyError, match="Invalid set payload for Tempo Press: no sets"):
        service.write_apply_request(46)


def test_sync_apply_allows_notes_preserved_nuance(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_notes_preserved_workout(store)
    service = TrueCoachToHevyReviewService(store=store, output_root=tmp_path / "reports")

    result = service.write_apply_request(50)

    exercise = result.request_body.model_dump()["routine"]["exercises"][0]
    assert exercise["notes"] == (
        "build weight then 3 x 12 ES alternating RIR 2, rest 60-90s\n"
        "Substitute dumbbells if benches are busy."
    )
    assert exercise["sets"] == [
        {
            "weight_kg": None,
            "reps": 12,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": 12,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
        {
            "weight_kg": None,
            "reps": 12,
            "distance_meters": None,
            "duration_seconds": None,
            "type": "normal",
        },
    ]


class _RecordingRoutineWriter:
    def __init__(self) -> None:
        self.requests: list[PostRoutinesRequestBody] = []

    def create_routine(self, routine: PostRoutinesRequestBody) -> None:
        self.requests.append(routine)


def _assert_mixed_knee_extension_blocks(item: dict) -> None:
    blocks = item["planned_blocks"]
    assert [block["source_id"] for block in blocks] == [1005, 1005]
    assert [block["block_kind"] for block in blocks] == ["isometric_hold", "dynamic_reps"]
    assert blocks[0]["source_text"] == "2 x 30s iso hold"
    assert blocks[0]["original_source_text"] == "Single Leg\n2 x 30s iso hold\n3 x 10-12"
    assert blocks[0]["notes"] == "2 x 30s iso hold\nSource: Single Leg\n2 x 30s iso hold\n3 x 10-12"
    assert blocks[0]["movement_name"] is None
    assert blocks[0]["movement_target"] is None
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
    assert blocks[0]["warnings"] == []
    assert blocks[0]["blockers"] == []
    assert blocks[1]["source_text"] == "3 x 10-12"
    assert blocks[1]["selected_hevy_template"]["id"] == "hevy-knee-extension"
    assert blocks[1]["required_hevy_templates"] == []
    assert blocks[1]["proposed_sets"] == [
        {"type": "normal", "reps": 12},
        {"type": "normal", "reps": 12},
        {"type": "normal", "reps": 12},
    ]
    assert blocks[1]["warnings"] == []
    assert blocks[1]["blockers"] == []


def _assert_resolved_amrap_movement_blocks(item: dict) -> None:
    blocks = item["planned_blocks"]
    assert item["source_id"] == 1011
    assert item["proposed_sets"] == []
    assert [block["block_kind"] for block in blocks] == [
        "amrap_movement",
        "amrap_movement",
    ]
    assert [
        (block["movement_name"], block["movement_target"], block["source_text"]) for block in blocks
    ] == [
        ("Bike", "500m", "Bike 500m"),
        ("Burpees", "10", "10 Burpees"),
    ]
    assert [block["original_source_text"] for block in blocks] == [
        "1. Bike 500m\n2. 10 Burpees\n3. 60s rest",
        "1. Bike 500m\n2. 10 Burpees\n3. 60s rest",
    ]
    assert [block["selected_hevy_template"]["id"] for block in blocks] == [
        "hevy-bike",
        "hevy-burpees",
    ]
    assert [block["proposed_sets"] for block in blocks] == [
        [{"type": "normal", "distance_meters": 500}],
        [{"type": "normal", "reps": 10}],
    ]
    assert [block["warnings"] for block in blocks] == [[], []]
    assert [block["blockers"] for block in blocks] == [[], []]
    assert item["warnings"] == []
    assert item["blockers"] == []


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
    assert (
        "- Add a True Coach to Hevy template mapping for True Coach Workout Item 1002 "
        '"Mystery Carry" with info "3 x 8+8+8 ^Glternating RIR 1" and comment "none".'
    ) in report
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
        uow.session.add(
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
        uow.session.add(TrueCoachExercise(id=501, name="Bench Press", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-bench",
                name="Barbell Bench Press",
                type="weight_reps",
                equipment="barbell",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(name="Bench Press", hevy_app_id="hevy-bench", true_coach_id=501)
        )
        uow.session.add(
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
        uow.session.add(
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


def _seed_circuit_block_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=51,
                title="Conditioning",
                due=now,
                short_description='<p class="name-and-info">A) 10\' AMRAP</p>',
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=511, name="10' AMRAP", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-conditioning",
                name="Conditioning",
                type="duration",
                equipment="none",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(name="10' AMRAP", hevy_app_id="hevy-conditioning", true_coach_id=511)
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1011,
                workout_id=51,
                name="10' AMRAP",
                info="1. Bike 500m\n2. 10 Burpees\n3. 60s rest",
                comment="",
                is_circuit=True,
                state="pending",
                position=1,
                exercise_id=511,
                assessment_id=None,
            )
        )


def _seed_circuit_movement_templates(store: Store) -> None:
    with store.unit_of_work() as uow:
        uow.session.add(TrueCoachExercise(id=512, name="Bike", default=False))
        uow.session.add(TrueCoachExercise(id=513, name="Burpees", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-bike",
                name="Bike",
                type="short_distance",
                equipment="machine",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-burpees",
                name="Burpees",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(TrackerExercise(name="Bike", hevy_app_id="hevy-bike", true_coach_id=512))
        uow.session.add(
            TrackerExercise(name="Burpees", hevy_app_id="hevy-burpees", true_coach_id=513)
        )


def _seed_round_ladder_circuit_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=53,
                title="Circuit Ladder",
                due=now,
                short_description='<p class="name-and-info">A) 3 Round Circuit</p>',
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=514, name="3 Round Circuit", default=False))
        uow.session.add(TrueCoachExercise(id=515, name="Goblet Squat", default=False))
        uow.session.add(TrueCoachExercise(id=516, name="Push Up", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-circuit",
                name="Circuit",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-goblet-squat",
                name="Goblet Squat",
                type="reps_only",
                equipment="dumbbell",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-push-up",
                name="Push Up",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="3 Round Circuit",
                hevy_app_id="hevy-circuit",
                true_coach_id=514,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="Goblet Squat",
                hevy_app_id="hevy-goblet-squat",
                true_coach_id=515,
            )
        )
        uow.session.add(
            TrackerExercise(name="Push Up", hevy_app_id="hevy-push-up", true_coach_id=516)
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1012,
                workout_id=53,
                name="3 Round Circuit",
                info="Goblet Squat\nPush Up\nRound 1: 12 reps\nRound 2: 10 reps\nRound 3: 8 reps",
                comment="",
                is_circuit=True,
                state="pending",
                position=1,
                exercise_id=514,
                assessment_id=None,
            )
        )


def _seed_circuit_template_override_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=54,
                title="Override Circuit",
                due=now,
                short_description='<p class="name-and-info">A) Single-leg iso circuit</p>',
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=517, name="Single-leg iso circuit", default=False))
        uow.session.add(TrueCoachExercise(id=518, name="Bodyweight Calf Raise", default=False))
        uow.session.add(TrueCoachExercise(id=519, name="Push Up", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-circuit",
                name="Circuit",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-calf-raise",
                name="Bodyweight Calf Raise",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-single-leg-calf-iso",
                name="Single-Leg Isometric Calf Raise",
                type="duration",
                equipment="bodyweight",
                default=False,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-push-up",
                name="Push Up",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="Single-leg iso circuit",
                hevy_app_id="hevy-circuit",
                true_coach_id=517,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="Bodyweight Calf Raise",
                hevy_app_id="hevy-calf-raise",
                true_coach_id=518,
            )
        )
        uow.session.add(
            TrackerExercise(name="Push Up", hevy_app_id="hevy-push-up", true_coach_id=519)
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1013,
                workout_id=54,
                name="Single-leg iso circuit",
                info="Bodyweight Calf Raise 20s\n10 Push Up",
                comment="single leg iso hold",
                is_circuit=True,
                state="pending",
                position=1,
                exercise_id=517,
                assessment_id=None,
            )
        )


def _seed_placeholder_circuit_movement_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=55,
                title="Placeholder Circuit",
                due=now,
                short_description='<p class="name-and-info">A) 10\' AMRAP</p>',
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=520, name="10' AMRAP", default=False))
        uow.session.add(TrueCoachExercise(id=521, name="Burpees", default=False))
        uow.session.add(TrueCoachExercise(id=522, name="Bike", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-placeholder",
                name="#####PLACEHOLDER#####",
                type="reps_only",
                equipment="bodyweight",
                default=False,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-bike",
                name="Bike",
                type="short_distance",
                equipment="machine",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(name="Burpees", hevy_app_id="hevy-placeholder", true_coach_id=521)
        )
        uow.session.add(TrackerExercise(name="Bike", hevy_app_id="hevy-bike", true_coach_id=522))
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1014,
                workout_id=55,
                name="10' AMRAP",
                info="10 Burpees\nBike 500m",
                comment="",
                is_circuit=True,
                state="pending",
                position=1,
                exercise_id=520,
                assessment_id=None,
            )
        )


def _seed_single_movement_circuit_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=56,
                title="Single Movement Circuit",
                due=now,
                short_description='<p class="name-and-info">A) Push Up</p>',
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=523, name="Push Up", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-push-up",
                name="Push Up",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(name="Push Up", hevy_app_id="hevy-push-up", true_coach_id=523)
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1015,
                workout_id=56,
                name="Push Up",
                info="3 x 10",
                comment="",
                is_circuit=True,
                state="pending",
                position=1,
                exercise_id=523,
                assessment_id=None,
            )
        )


def _seed_round_circuit_request_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=57,
                title="Round Circuit Request",
                due=now,
                short_description='<p class="name-and-info">A) 3 Round Circuit</p>',
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=524, name="3 Round Circuit", default=False))
        uow.session.add(TrueCoachExercise(id=525, name="Burpees", default=False))
        uow.session.add(TrueCoachExercise(id=526, name="Plank", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-circuit",
                name="Circuit",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-burpees",
                name="Burpees",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-plank",
                name="Plank",
                type="duration",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="3 Round Circuit",
                hevy_app_id="hevy-circuit",
                true_coach_id=524,
            )
        )
        uow.session.add(
            TrackerExercise(name="Burpees", hevy_app_id="hevy-burpees", true_coach_id=525)
        )
        uow.session.add(TrackerExercise(name="Plank", hevy_app_id="hevy-plank", true_coach_id=526))
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1016,
                workout_id=57,
                name="3 Round Circuit",
                info="10 Burpees\nPlank 30s\nRest 15s between each exercise and 60s between each round",
                comment="",
                is_circuit=True,
                state="pending",
                position=1,
                exercise_id=524,
                assessment_id=None,
            )
        )


def _seed_notes_only_circuit_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=59,
                title="Notes Only Circuit",
                due=now,
                short_description='<p class="name-and-info">A) 1 Round Circuit</p>',
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=531, name="1 Round Circuit", default=False))
        uow.session.add(TrueCoachExercise(id=532, name="Bike", default=False))
        uow.session.add(TrueCoachExercise(id=533, name="Burpees", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-circuit",
                name="Circuit",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-bike",
                name="Bike",
                type="short_distance",
                equipment="machine",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-burpees",
                name="Burpees",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="1 Round Circuit",
                hevy_app_id="hevy-circuit",
                true_coach_id=531,
            )
        )
        uow.session.add(TrackerExercise(name="Bike", hevy_app_id="hevy-bike", true_coach_id=532))
        uow.session.add(
            TrackerExercise(name="Burpees", hevy_app_id="hevy-burpees", true_coach_id=533)
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1019,
                workout_id=59,
                name="1 Round Circuit",
                info="15 cals Bike\n10 Burpees",
                comment="",
                is_circuit=True,
                state="pending",
                position=1,
                exercise_id=531,
                assessment_id=None,
            )
        )


def _seed_superset_and_standalone_circuit_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=58,
                title="Superset Circuit Request",
                due=now,
                short_description=(
                    '<p class="name-and-info">'
                    "A1) Push Up<br/>"
                    "A2) 2 Round Circuit<br/>"
                    "B) 2 Round Finisher"
                    "</p>"
                ),
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        exercise_rows = [
            (527, "Push Up", "hevy-push-up", "reps_only", "bodyweight"),
            (528, "2 Round Circuit", "hevy-circuit", "reps_only", "bodyweight"),
            (529, "Burpees", "hevy-burpees", "reps_only", "bodyweight"),
            (530, "Plank", "hevy-plank", "duration", "bodyweight"),
            (531, "2 Round Finisher", "hevy-finisher", "reps_only", "bodyweight"),
            (532, "Bike", "hevy-bike", "short_distance", "machine"),
        ]
        for exercise_id, name, hevy_id, exercise_type, equipment in exercise_rows:
            uow.session.add(TrueCoachExercise(id=exercise_id, name=name, default=False))
            uow.session.add(
                HevyAppExercise(
                    id=hevy_id,
                    name=name,
                    type=exercise_type,
                    equipment=equipment,
                    default=True,
                )
            )
            uow.session.add(
                TrackerExercise(name=name, hevy_app_id=hevy_id, true_coach_id=exercise_id)
            )
        items = [
            (1017, "Push Up", "1 x 5", False, 1, 527),
            (1018, "2 Round Circuit", "10 Burpees\nPlank 30s", True, 2, 528),
            (1019, "2 Round Finisher", "Bike 500m\n10 Burpees", True, 3, 531),
        ]
        for item_id, name, info, is_circuit, position, exercise_id in items:
            uow.session.add(
                TrueCoachWorkoutItem(
                    id=item_id,
                    workout_id=58,
                    name=name,
                    info=info,
                    comment="",
                    is_circuit=is_circuit,
                    state="pending",
                    position=position,
                    exercise_id=exercise_id,
                    assessment_id=None,
                )
            )


def _seed_bench_history(store: Store) -> None:
    _seed_bench_normal_history(store, reps=12, weight_kg=80.0)


def _seed_sled_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=48,
                title="Sled Day",
                due=now,
                short_description='<p class="name-and-info">A) Sled Push</p>',
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=508, name="Sled Push", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-sled",
                name="Sled Push (Weight & Distance)",
                type="short_distance_weight",
                equipment="other",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(name="Sled Push", hevy_app_id="hevy-sled", true_coach_id=508)
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1008,
                workout_id=48,
                name="Sled Push",
                info="2 x 1L\n- 120kg of plates",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=508,
                assessment_id=None,
            )
        )


def _seed_sled_history(store: Store) -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppWorkout(
                id="hevy-sled-history-1",
                title="Sled Day Logged",
                description="",
                start_time=now,
                end_time=now,
            )
        )
        uow.session.add(
            HevyAppWorkoutItem(
                id=2008,
                workout_id="hevy-sled-history-1",
                index=0,
                name="Sled Push (Weight & Distance)",
                notes="",
                superset_id=None,
                exercise_id="hevy-sled",
            )
        )
        for index in range(2):
            uow.session.add(
                HevyAppSets(
                    workout_item_id=2008,
                    index=index,
                    type="normal",
                    weight_kg=120.0,
                    distance_meters=10,
                )
            )


def _seed_bench_normal_history(store: Store, *, reps: int, weight_kg: float) -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppWorkout(
                id="hevy-history-1",
                title="Upper Strength Logged",
                description="",
                start_time=now,
                end_time=now,
            )
        )
        uow.session.add(
            HevyAppWorkoutItem(
                id=2001,
                workout_id="hevy-history-1",
                index=0,
                name="Barbell Bench Press",
                notes="",
                superset_id=None,
                exercise_id="hevy-bench",
            )
        )
        for index in range(3):
            uow.session.add(
                HevyAppSets(
                    workout_item_id=2001,
                    index=index,
                    type="normal",
                    weight_kg=weight_kg,
                    reps=reps,
                )
            )


def _seed_bench_dropset_history(store: Store) -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    rows = [
        ("normal", 100.0),
        ("dropset", 82.5),
        ("normal", 100.0),
        ("dropset", 80.0),
    ]
    with store.unit_of_work() as uow:
        uow.session.add(
            HevyAppWorkout(
                id="hevy-dropset-history-1",
                title="Upper Strength Logged",
                description="",
                start_time=now,
                end_time=now,
            )
        )
        uow.session.add(
            HevyAppWorkoutItem(
                id=2002,
                workout_id="hevy-dropset-history-1",
                index=0,
                name="Barbell Bench Press",
                notes="",
                superset_id=None,
                exercise_id="hevy-bench",
            )
        )
        for index, (set_type, weight_kg) in enumerate(rows):
            uow.session.add(
                HevyAppSets(
                    workout_item_id=2002,
                    index=index,
                    type=set_type,
                    weight_kg=weight_kg,
                    reps=10,
                )
            )


def _seed_template_override_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
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
        uow.session.add(TrueCoachExercise(id=502, name="Bodyweight Calf Raise", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-calf-raise",
                name="Bodyweight Calf Raise",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="Bodyweight Calf Raise",
                hevy_app_id="hevy-calf-raise",
                true_coach_id=502,
            )
        )
        uow.session.add(
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
        uow.session.add(
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
        uow.session.add(TrueCoachExercise(id=503, name="Seated Knee Extension", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-knee-extension",
                name="Seated Knee Extension",
                type="reps_only",
                equipment="machine",
                default=True,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-knee-iso-a",
                name="Isometric Seated Knee Extension",
                type="duration",
                equipment="machine",
                default=False,
            )
        )
        uow.session.add(
            HevyAppExercise(
                id="hevy-knee-iso-b",
                name="Isometric Seated Knee Extension",
                type="duration",
                equipment="machine",
                default=False,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="Seated Knee Extension",
                hevy_app_id="hevy-knee-extension",
                true_coach_id=503,
            )
        )
        uow.session.add(
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
        uow.session.add(
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
        uow.session.add(TrueCoachExercise(id=504, name="Seated Knee Extension", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-knee-extension",
                name="Seated Knee Extension",
                type="reps_only",
                equipment="machine",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="Seated Knee Extension",
                hevy_app_id="hevy-knee-extension",
                true_coach_id=504,
            )
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1005,
                workout_id=45,
                name="Seated Knee Extension",
                info="Single Leg\n2 x 30s iso hold\n3 x 10-12",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=504,
                assessment_id=None,
            )
        )


def _seed_parser_gap_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=46,
                title="Parser Gap",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=505, name="Tempo Press", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-tempo-press",
                name="Tempo Press",
                type="reps_only",
                equipment="dumbbell",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(name="Tempo Press", hevy_app_id="hevy-tempo-press", true_coach_id=505)
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1006,
                workout_id=46,
                name="Tempo Press",
                info="tempo eccentric clusters to technical failure",
                comment="coach wants controlled eccentrics",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=505,
                assessment_id=None,
            )
        )


def _seed_clean_plan_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=47,
                title="Clean Plan",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=506, name="Push Up", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-push-up",
                name="Push Up",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(name="Push Up", hevy_app_id="hevy-push-up", true_coach_id=506)
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1007,
                workout_id=47,
                name="Push Up",
                info="3 x 12",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=506,
                assessment_id=None,
            )
        )


def _seed_superset_plan_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    exercises = [
        (520, "Cat Cow", "hevy-cat-cow"),
        (521, "Bent Knee Lumbar Rotations", "hevy-lumbar-rotations"),
        (522, "Banded Good Morning", "hevy-good-morning"),
        (523, "Spanish Squat Iso", "hevy-spanish-squat"),
        (524, "Bulgarians", "hevy-bulgarians"),
    ]
    items = [
        (1020, "Cat Cow", 520, 1),
        (1021, "Bent Knee Lumbar Rotations", 521, 2),
        (1022, "Banded Good Morning", 522, 3),
        (1023, "Spanish Squat Iso", 523, 4),
        (1024, "Bulgarians", 524, 5),
    ]
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=52,
                title="Superset Plan",
                due=now,
                short_description=(
                    '<p class="name-and-info">'
                    "A1) Cat Cow<br/>"
                    "A2) Bent Knee Lumbar Rotations<br/>"
                    "B1) Banded Good Morning<br/>"
                    "B2) Spanish Squat Iso<br/>"
                    "C) Bulgarians"
                    "</p>"
                ),
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        for exercise_id, name, hevy_id in exercises:
            uow.session.add(TrueCoachExercise(id=exercise_id, name=name, default=False))
            uow.session.add(
                HevyAppExercise(
                    id=hevy_id,
                    name=name,
                    type="reps_only",
                    equipment="bodyweight",
                    default=True,
                )
            )
            uow.session.add(
                TrackerExercise(name=name, hevy_app_id=hevy_id, true_coach_id=exercise_id)
            )
        for item_id, name, exercise_id, position in items:
            uow.session.add(
                TrueCoachWorkoutItem(
                    id=item_id,
                    workout_id=52,
                    name=name,
                    info="1 x 5",
                    comment="",
                    is_circuit=False,
                    state="pending",
                    position=position,
                    exercise_id=exercise_id,
                    assessment_id=None,
                )
            )


def _seed_clean_weight_plan_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=48,
                title="Pull Strength",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=507, name="Row", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-row",
                name="Row",
                type="weight_reps",
                equipment="barbell",
                default=True,
            )
        )
        uow.session.add(TrackerExercise(name="Row", hevy_app_id="hevy-row", true_coach_id=507))
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1008,
                workout_id=48,
                name="Row",
                info="2 x 10",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=507,
                assessment_id=None,
            )
        )


def _seed_clean_duration_plan_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=51,
                title="Duration Plan",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=510, name="Couch Stretch", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-couch-stretch",
                name="Couch Stretch",
                type="duration",
                equipment="none",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="Couch Stretch",
                hevy_app_id="hevy-couch-stretch",
                true_coach_id=510,
            )
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1010,
                workout_id=51,
                name="Couch Stretch",
                info="1 x 30s then 1 x 45s",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=510,
                assessment_id=None,
            )
        )


def _seed_cardio_duration_plan_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=59,
                title="Cardio Duration Plan",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=533, name="Bike", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-bike",
                name="Bike",
                type="duration",
                equipment="machine",
                default=True,
            )
        )
        uow.session.add(TrackerExercise(name="Bike", hevy_app_id="hevy-bike", true_coach_id=533))
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1020,
                workout_id=59,
                name="Bike",
                info="1 x 30s",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=533,
                assessment_id=None,
            )
        )


def _seed_unsplit_mixed_mode_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=49,
                title="Knee Rehab Unsplit",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=508, name="Seated Knee Extension", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-knee-extension",
                name="Seated Knee Extension",
                type="reps_only",
                equipment="machine",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(
                name="Seated Knee Extension",
                hevy_app_id="hevy-knee-extension",
                true_coach_id=508,
            )
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1009,
                workout_id=49,
                name="Seated Knee Extension",
                info="2 x 30s iso hold then tempo reps",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=508,
                assessment_id=None,
            )
        )


def _seed_notes_preserved_workout(store: Store) -> None:
    now = datetime(2026, 5, 17, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=50,
                title="Nuance Day",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=509, name="Bench Press", default=False))
        uow.session.add(
            HevyAppExercise(
                id="hevy-bench",
                name="Barbell Bench Press",
                type="weight_reps",
                equipment="barbell",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(name="Bench Press", hevy_app_id="hevy-bench", true_coach_id=509)
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1010,
                workout_id=50,
                name="Bench Press",
                info="build weight then 3 x 12 ES alternating RIR 2, rest 60-90s",
                comment="Substitute dumbbells if benches are busy.",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=509,
                assessment_id=None,
            )
        )
