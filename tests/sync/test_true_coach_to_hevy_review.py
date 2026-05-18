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
            "notes": "",
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


def _seed_bench_history(store: Store) -> None:
    _seed_bench_normal_history(store, reps=12, weight_kg=80.0)


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
                info="2 x 30s iso hold then 3 x 10-12",
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
