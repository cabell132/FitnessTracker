from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from fitness_tracker.apis.true_coach.exceptions import TrueCoachAPIError
from fitness_tracker.apis.true_coach.types import PutWorkoutItemRequest
from fitness_tracker.apis.true_coach.types import Workout as TrueCoachWorkoutPayload
from fitness_tracker.apis.true_coach.types import WorkoutItem as TrueCoachWorkoutItemPayload
from fitness_tracker.cli import main
from fitness_tracker.database import Store
from fitness_tracker.database.models.hevy_app import (
    HevyAppExercise,
    HevyAppSets,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.models.tracker import (
    Exercise as TrackerExercise,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import (
    TrueCoachExercise,
    TrueCoachWorkout,
    TrueCoachWorkoutItem,
)
from fitness_tracker.sync_review import (
    HevyToTrueCoachResultApplyError,
    HevyToTrueCoachResultReviewService,
)


def test_hevy_to_truecoach_result_review_cli_writes_read_only_artifacts(  # noqa: PLR0915
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)

    exit_code = main(
        [
            "sync-review",
            "hevy-to-truecoach-results",
            "--workout-id",
            "hevy-result-1",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    bundle_dir = (
        tmp_path / "reports" / "sync-review" / "hevy-to-truecoach-results" / "hevy-result-1"
    )
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    decisions = json.loads((bundle_dir / "result-decisions.json").read_text(encoding="utf-8"))
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))
    report = (bundle_dir / "report.md").read_text(encoding="utf-8")

    assert plan["workout"] == {
        "hevy_workout_id": "hevy-result-1",
        "title": "Upper Result",
        "true_coach_workout_id": 9001,
        "true_coach_title": "Upper Result",
    }
    assert [item["hevy_workout_item_id"] for item in plan["items"]] == [
        1,
        2,
        3,
        4,
    ]
    assert plan["items"][0]["target"]["true_coach_workout_item_id"] == 9101
    assert plan["items"][0]["formatter"] == "weight_reps"
    assert plan["items"][0]["proposed_result_text"] == "8 x 80.0 kg\n7 x 80.0 kg"
    assert plan["items"][0]["sets"] == [
        {
            "index": 0,
            "type": "normal",
            "weight_kg": 80.0,
            "reps": 8,
            "distance_meters": None,
            "duration_seconds": None,
            "rpe": None,
        },
        {
            "index": 1,
            "type": "normal",
            "weight_kg": 80.0,
            "reps": 7,
            "distance_meters": None,
            "duration_seconds": None,
            "rpe": None,
        },
    ]
    assert plan["items"][1]["blockers"] == [
        "Unsupported Hevy exercise type for True Coach result formatting: custom_metric"
    ]
    assert plan["items"][2]["blockers"] == [
        "Ambiguous True Coach target for unlinked performed Hevy item: 2 candidates"
    ]
    assert [
        candidate["true_coach_workout_item_id"] for candidate in plan["items"][2]["candidates"]
    ] == [
        9103,
        9104,
    ]
    assert plan["items"][3]["blockers"] == [
        "Missing True Coach Workout Item link for performed Hevy item"
    ]
    assert "would_call_true_coach_api" not in json.dumps(plan)

    assert decisions["hevy_workout_id"] == "hevy-result-1"
    assert decisions["items"][0] == {
        "hevy_workout_item_id": 1,
        "action": "sync",
        "override_true_coach_workout_item_id": None,
        "performed_as": None,
        "order_context": None,
        "omit_reason": None,
    }
    assert validation["blockers"] == plan["blockers"]
    assert "Unsupported Hevy exercise type" in report
    assert "Proposed result:" in report
    assert "8 x 80.0 kg" in report

    output = capsys.readouterr().out
    assert f"review_dir: {bundle_dir}" in output
    assert f"report: {bundle_dir / 'report.md'}" in output
    assert f"plan: {bundle_dir / 'plan.json'}" in output
    assert f"decisions: {bundle_dir / 'result-decisions.json'}" in output
    assert f"decision_validation: {bundle_dir / 'decision-validation.json'}" in output
    assert "blockers: 3" in output
    assert "warnings: 1" in output


def test_hevy_to_truecoach_result_review_validates_mapping_override(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": False,
                "approve_completion": False,
                "items": [
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9103,
                        "performed_as": "Chest Supported Row",
                        "order_context": None,
                        "omit_reason": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "sync-review",
            "hevy-to-truecoach-results",
            "--workout-id",
            "hevy-result-1",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
            "--decisions",
            str(decisions_path),
        ]
    )

    assert exit_code == 0
    bundle_dir = (
        tmp_path / "reports" / "sync-review" / "hevy-to-truecoach-results" / "hevy-result-1"
    )
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))
    decisions = json.loads((bundle_dir / "result-decisions.json").read_text(encoding="utf-8"))
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))

    assert plan["items"][2]["blockers"] == [
        "Ambiguous True Coach target for unlinked performed Hevy item: 2 candidates"
    ]
    assert decisions["items"] == [
        {
            "hevy_workout_item_id": 3,
            "action": "sync",
            "override_true_coach_workout_item_id": 9103,
            "performed_as": "Chest Supported Row",
            "order_context": None,
            "omit_reason": None,
        }
    ]
    assert not any("Ambiguous True Coach target" in blocker for blocker in validation["blockers"])


def test_hevy_to_truecoach_result_review_requires_omit_reason(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)

    validation_without_reason = _write_review_with_decisions(
        tmp_path,
        db_path,
        {
            "hevy_workout_id": "hevy-result-1",
            "items": [{"hevy_workout_item_id": 4, "action": "omit", "omit_reason": ""}],
        },
    )
    validation_with_reason = _write_review_with_decisions(
        tmp_path,
        db_path,
        {
            "hevy_workout_id": "hevy-result-1",
            "items": [
                {
                    "hevy_workout_item_id": 4,
                    "action": "omit",
                    "omit_reason": "Accidental extra Hevy block",
                }
            ],
        },
    )

    assert (
        "Hevy item 4 is omitted without a required reason" in validation_without_reason["blockers"]
    )
    assert (
        "Hevy item 4 is omitted without a required reason" not in validation_with_reason["blockers"]
    )
    assert not any(
        blocker == "Missing True Coach Workout Item link for performed Hevy item"
        for blocker in validation_with_reason["blockers"]
    )


def test_hevy_to_truecoach_result_review_disambiguates_repeated_exercises_by_sets_and_reps(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    _replace_row_work_with_repeated_warmup_and_main(store, ambiguous=False)

    exit_code = main(
        [
            "sync-review",
            "hevy-to-truecoach-results",
            "--workout-id",
            "hevy-result-1",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    bundle_dir = (
        tmp_path / "reports" / "sync-review" / "hevy-to-truecoach-results" / "hevy-result-1"
    )
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))
    plan = json.loads((bundle_dir / "plan.json").read_text(encoding="utf-8"))

    row_items = [item for item in plan["items"] if item["name"] == "Chest Supported Row"]
    assert [
        [candidate["true_coach_workout_item_id"] for candidate in item["candidates"]]
        for item in row_items
    ] == [[9103], [9104]]
    assert not any("Chest Supported Row" in blocker for blocker in validation["blockers"])
    assert not any("Ambiguous True Coach target" in blocker for blocker in validation["blockers"])


def test_hevy_to_truecoach_result_review_blocks_ambiguous_repeated_exercises(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    _replace_row_work_with_repeated_warmup_and_main(store, ambiguous=True)

    exit_code = main(
        [
            "sync-review",
            "hevy-to-truecoach-results",
            "--workout-id",
            "hevy-result-1",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    bundle_dir = (
        tmp_path / "reports" / "sync-review" / "hevy-to-truecoach-results" / "hevy-result-1"
    )
    validation = json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))

    assert any("Ambiguous True Coach target" in blocker for blocker in validation["blockers"])


def test_hevy_to_truecoach_result_review_blocks_duplicate_decision_mappings(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)

    validation = _write_review_with_decisions(
        tmp_path,
        db_path,
        {
            "hevy_workout_id": "hevy-result-1",
            "items": [
                {
                    "hevy_workout_item_id": 3,
                    "action": "sync",
                    "override_true_coach_workout_item_id": 9103,
                },
                {
                    "hevy_workout_item_id": 3,
                    "action": "sync",
                    "override_true_coach_workout_item_id": 9104,
                },
            ],
        },
    )

    assert any(
        "Hevy item 3 is mapped more than once" in blocker for blocker in validation["blockers"]
    )


def test_hevy_to_truecoach_result_review_blocks_unsafe_completion(tmp_path: Path) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)

    validation = _write_review_with_decisions(
        tmp_path,
        db_path,
        {
            "hevy_workout_id": "hevy-result-1",
            "approve_completion": True,
            "items": [],
        },
    )

    assert (
        "Completion approval is unsafe while result mapping blockers remain"
        in validation["blockers"]
    )


def test_hevy_to_truecoach_result_apply_dry_run_writes_update_request(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": False,
                "approve_completion": False,
                "items": [
                    {"hevy_workout_item_id": 1, "action": "sync"},
                    {
                        "hevy_workout_item_id": 2,
                        "action": "omit",
                        "omit_reason": "Unsupported custom metric result.",
                    },
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9103,
                    },
                    {
                        "hevy_workout_item_id": 4,
                        "action": "omit",
                        "omit_reason": "Accidental extra Hevy block.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    service = HevyToTrueCoachResultReviewService(store=store, output_root=tmp_path / "reports")

    dry_run = service.write_apply_request("hevy-result-1", decisions_path=decisions_path)

    request = json.loads(dry_run.request_path.read_text(encoding="utf-8"))
    assert dry_run.action == "dry_run"
    assert request["workout_id"] == 9001
    assert request["mark_workout_completed"] is False
    assert request["completion_status"] == "skipped"
    assert request["update_workout_items"][0] == {
        "method": "PUT",
        "endpoint": "workout_items/9101",
        "body": {
            "workout_item": {
                "id": 9101,
                "workout_id": 9001,
                "name": "Bench Press",
                "info": "2 x 8",
                "result": "8 x 80.0 kg\n7 x 80.0 kg",
                "is_circuit": False,
                "state": "completed",
                "state_event": "mark_as_completed",
                "position": 1,
                "assessment_id": None,
                "exercise_id": 701,
            }
        },
    }


def test_hevy_to_truecoach_result_apply_wraps_replacement_and_order_context(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": False,
                "items": [
                    {"hevy_workout_item_id": 1, "action": "sync"},
                    {
                        "hevy_workout_item_id": 2,
                        "action": "omit",
                        "omit_reason": "Unsupported custom metric result.",
                    },
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9103,
                        "performed_as": "Chest Supported Row instead of cable row",
                        "order_context": "Performed after bench due to equipment availability.",
                    },
                    {
                        "hevy_workout_item_id": 4,
                        "action": "omit",
                        "omit_reason": "Accidental extra Hevy block.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    service = HevyToTrueCoachResultReviewService(store=store, output_root=tmp_path / "reports")

    dry_run = service.write_apply_request("hevy-result-1", decisions_path=decisions_path)

    request = json.loads(dry_run.request_path.read_text(encoding="utf-8"))
    row_result = request["update_workout_items"][1]["body"]["workout_item"]["result"]
    assert row_result == (
        "Performed as: Chest Supported Row instead of cable row\n"
        "Order context: Performed after bench due to equipment availability.\n"
        "10 x 55.0 kg"
    )


def test_hevy_to_truecoach_result_apply_refuses_unresolved_blockers(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    service = HevyToTrueCoachResultReviewService(store=store, output_root=tmp_path / "reports")

    with pytest.raises(HevyToTrueCoachResultApplyError, match="Unsupported Hevy exercise type"):
        service.write_apply_request("hevy-result-1")


def test_hevy_to_truecoach_result_apply_partial_refuses_duplicate_mappings(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": True,
                "items": [
                    {"hevy_workout_item_id": 1, "action": "sync"},
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9101,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    service = HevyToTrueCoachResultReviewService(store=store, output_root=tmp_path / "reports")

    with pytest.raises(
        HevyToTrueCoachResultApplyError,
        match="receives multiple performed Hevy items",
    ):
        service.write_apply_request("hevy-result-1", decisions_path=decisions_path)


def test_hevy_to_truecoach_result_apply_allows_partial_apply_for_resolved_items(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": True,
                "approve_completion": True,
                "items": [
                    {"hevy_workout_item_id": 1, "action": "sync"},
                    {
                        "hevy_workout_item_id": 2,
                        "action": "omit",
                        "omit_reason": "Unsupported custom metric result.",
                    },
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9103,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    service = HevyToTrueCoachResultReviewService(store=store, output_root=tmp_path / "reports")

    dry_run = service.write_apply_request("hevy-result-1", decisions_path=decisions_path)

    request = json.loads(dry_run.request_path.read_text(encoding="utf-8"))
    assert request["mark_workout_completed"] is False
    assert request["completion_status"] == "blocked"
    assert [update["body"]["workout_item"]["id"] for update in request["update_workout_items"]] == [
        9101,
        9103,
    ]


def test_hevy_to_truecoach_result_apply_dry_run_cli_writes_request(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = _write_safe_apply_decisions(tmp_path)

    exit_code = main(
        [
            "sync-apply",
            "hevy-to-truecoach-results",
            "--workout-id",
            "hevy-result-1",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
            "--decisions",
            str(decisions_path),
            "--dry-run",
        ]
    )

    request_path = (
        tmp_path
        / "reports"
        / "sync-review"
        / "hevy-to-truecoach-results"
        / "hevy-result-1"
        / "truecoach-update-request.json"
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert request["update_workout_items"][0]["endpoint"] == "workout_items/9101"
    output = capsys.readouterr().out
    assert f"review_dir: {request_path.parent}" in output
    assert f"request: {request_path}" in output
    assert "blockers: 0" in output
    assert "warnings: 1" in output
    assert "action: dry_run" in output
    assert "updated_true_coach_workout_item_ids: [9101, 9103]" in output
    assert "omitted_hevy_workout_item_ids: [2, 4]" in output
    assert "unresolved_hevy_workout_item_ids: []" in output
    assert "completion_status: skipped" in output


def test_hevy_to_truecoach_result_apply_cli_refuses_unresolved_blockers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)

    exit_code = main(
        [
            "sync-apply",
            "hevy-to-truecoach-results",
            "--workout-id",
            "hevy-result-1",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
            "--dry-run",
        ]
    )

    assert exit_code == 2
    assert "Unsupported Hevy exercise type" in capsys.readouterr().out


def test_hevy_to_truecoach_result_apply_cli_refuses_invalid_decisions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": True,
                "items": [
                    {"hevy_workout_item_id": 1, "action": "sync"},
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9101,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "sync-apply",
            "hevy-to-truecoach-results",
            "--workout-id",
            "hevy-result-1",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
            "--decisions",
            str(decisions_path),
            "--dry-run",
        ]
    )

    assert exit_code == 2
    assert "receives multiple performed Hevy items" in capsys.readouterr().out


def test_hevy_to_truecoach_result_apply_cli_refuses_real_apply_without_confirmation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = _write_safe_apply_decisions(tmp_path)

    exit_code = main(
        [
            "sync-apply",
            "hevy-to-truecoach-results",
            "--workout-id",
            "hevy-result-1",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
            "--decisions",
            str(decisions_path),
        ]
    )

    assert exit_code == 2
    assert "Error: real apply requires --yes" in capsys.readouterr().out


def test_hevy_to_truecoach_result_apply_cli_sends_real_apply_with_fake_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": False,
                "approve_completion": True,
                "items": [
                    {"hevy_workout_item_id": 1, "action": "sync"},
                    {
                        "hevy_workout_item_id": 2,
                        "action": "omit",
                        "omit_reason": "Unsupported custom metric result.",
                    },
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9103,
                    },
                    {
                        "hevy_workout_item_id": 4,
                        "action": "omit",
                        "omit_reason": "Accidental extra Hevy block.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    writer = _RecordingTrueCoachWorkoutItemWriter()
    monkeypatch.setattr("fitness_tracker.cli.Config.from_env", lambda: _FakeConfig())
    monkeypatch.setattr("fitness_tracker.cli.TrueCoachClient", lambda **_: object())
    monkeypatch.setattr(
        "fitness_tracker.cli.TrueCoachWorkoutItemWriterAdapter",
        lambda _client: writer,
    )

    exit_code = main(
        [
            "sync-apply",
            "hevy-to-truecoach-results",
            "--workout-id",
            "hevy-result-1",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
            "--decisions",
            str(decisions_path),
            "--yes",
        ]
    )

    assert exit_code == 0
    assert [item_id for item_id, _ in writer.update_requests] == [9101, 9103]
    assert writer.completed_workout_ids == [9001]
    output = capsys.readouterr().out
    assert "action: applied" in output
    assert "completion_status: performed" in output


def test_hevy_to_truecoach_result_apply_sends_full_reviewed_updates(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": False,
                "approve_completion": True,
                "items": [
                    {"hevy_workout_item_id": 1, "action": "sync"},
                    {
                        "hevy_workout_item_id": 2,
                        "action": "omit",
                        "omit_reason": "Unsupported custom metric result.",
                    },
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9103,
                    },
                    {
                        "hevy_workout_item_id": 4,
                        "action": "omit",
                        "omit_reason": "Accidental extra Hevy block.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    service = HevyToTrueCoachResultReviewService(store=store, output_root=tmp_path / "reports")
    writer = _RecordingTrueCoachWorkoutItemWriter()

    applied = service.apply(
        "hevy-result-1",
        workout_item_writer=writer,
        decisions_path=decisions_path,
    )

    assert [item_id for item_id, _ in writer.update_requests] == [9101, 9103]
    assert writer.completed_workout_ids == [9001]
    assert applied.updated_true_coach_workout_item_ids == [9101, 9103]
    assert applied.omitted_hevy_workout_item_ids == [2, 4]
    assert applied.unresolved_hevy_workout_item_ids == []


def test_hevy_to_truecoach_result_apply_refreshes_stale_item_and_retries_safely(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": False,
                "approve_completion": True,
                "items": [
                    {"hevy_workout_item_id": 1, "action": "sync"},
                    {
                        "hevy_workout_item_id": 2,
                        "action": "omit",
                        "omit_reason": "Unsupported custom metric result.",
                    },
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9103,
                    },
                    {
                        "hevy_workout_item_id": 4,
                        "action": "omit",
                        "omit_reason": "Accidental extra Hevy block.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    service = HevyToTrueCoachResultReviewService(store=store, output_root=tmp_path / "reports")
    writer = _RefreshingTrueCoachWorkoutItemWriter(
        stale_item_id=9101,
        replacement_item=_true_coach_workout_item_payload(
            item_id=9201,
            name="Bench Press",
            position=1,
        ),
    )

    applied = service.apply(
        "hevy-result-1",
        workout_item_writer=writer,
        decisions_path=decisions_path,
    )

    assert [item_id for item_id, _ in writer.update_requests] == [9101, 9201, 9103]
    assert writer.completed_workout_ids == [9001]
    assert writer.refresh_requests == [9001]
    assert applied.updated_true_coach_workout_item_ids == [9201, 9103]
    assert applied.unresolved_hevy_workout_item_ids == []
    assert applied.request["completion_status"] == "performed"


def test_hevy_to_truecoach_result_apply_sends_partial_reviewed_updates(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "tracker.sqlite"
    store = Store(create_engine(f"sqlite:///{db_path}"))
    store.init_db()
    _seed_result_review_workout(store)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": True,
                "approve_completion": True,
                "items": [
                    {"hevy_workout_item_id": 1, "action": "sync"},
                    {
                        "hevy_workout_item_id": 2,
                        "action": "omit",
                        "omit_reason": "Unsupported custom metric result.",
                    },
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9103,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    service = HevyToTrueCoachResultReviewService(store=store, output_root=tmp_path / "reports")
    dry_run = service.write_apply_request("hevy-result-1", decisions_path=decisions_path)
    writer = _RecordingTrueCoachWorkoutItemWriter()

    applied = service.apply(
        "hevy-result-1",
        workout_item_writer=writer,
        decisions_path=decisions_path,
    )

    dry_run_request = json.loads(dry_run.request_path.read_text(encoding="utf-8"))
    assert dry_run_request["completion_status"] == "blocked"
    assert [request.model_dump() for _, request in writer.update_requests] == [
        update["body"]["workout_item"] for update in dry_run_request["update_workout_items"]
    ]
    assert [item_id for item_id, _ in writer.update_requests] == [9101, 9103]
    assert writer.completed_workout_ids == []
    assert applied.action == "applied"
    assert applied.updated_true_coach_workout_item_ids == [9101, 9103]
    assert applied.omitted_hevy_workout_item_ids == [2]
    assert applied.unresolved_hevy_workout_item_ids == [4]


def _write_review_with_decisions(
    tmp_path: Path,
    db_path: Path,
    decisions: dict[str, object],
) -> dict[str, object]:
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(json.dumps(decisions), encoding="utf-8")

    exit_code = main(
        [
            "sync-review",
            "hevy-to-truecoach-results",
            "--workout-id",
            "hevy-result-1",
            "--database-url",
            f"sqlite:///{db_path}",
            "--output-dir",
            str(tmp_path / "reports"),
            "--decisions",
            str(decisions_path),
        ]
    )

    assert exit_code == 0
    bundle_dir = (
        tmp_path / "reports" / "sync-review" / "hevy-to-truecoach-results" / "hevy-result-1"
    )
    return json.loads((bundle_dir / "decision-validation.json").read_text(encoding="utf-8"))


def _write_safe_apply_decisions(tmp_path: Path) -> Path:
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "hevy_workout_id": "hevy-result-1",
                "allow_partial_apply": False,
                "approve_completion": False,
                "items": [
                    {"hevy_workout_item_id": 1, "action": "sync"},
                    {
                        "hevy_workout_item_id": 2,
                        "action": "omit",
                        "omit_reason": "Unsupported custom metric result.",
                    },
                    {
                        "hevy_workout_item_id": 3,
                        "action": "sync",
                        "override_true_coach_workout_item_id": 9103,
                    },
                    {
                        "hevy_workout_item_id": 4,
                        "action": "omit",
                        "omit_reason": "Accidental extra Hevy block.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return decisions_path


class _RecordingTrueCoachWorkoutItemWriter:
    def __init__(self) -> None:
        self.update_requests: list[tuple[int, PutWorkoutItemRequest]] = []
        self.completed_workout_ids: list[int] = []

    def update_workout_item(self, item_id: int, item: PutWorkoutItemRequest) -> None:
        self.update_requests.append((item_id, item))

    def mark_workout_completed(self, workout_id: int) -> None:
        self.completed_workout_ids.append(workout_id)


class _FakeSecret:
    def get_secret_value(self) -> str:
        return "secret"


class _FakeConfig:
    email = "athlete@example.com"
    truecoach_password = _FakeSecret()


class _RefreshingTrueCoachWorkoutItemWriter(_RecordingTrueCoachWorkoutItemWriter):
    def __init__(
        self,
        *,
        stale_item_id: int,
        replacement_item: TrueCoachWorkoutItemPayload,
    ) -> None:
        super().__init__()
        self._stale_item_id = stale_item_id
        self._replacement_item = replacement_item
        self.refresh_requests: list[int] = []

    def update_workout_item(self, item_id: int, item: PutWorkoutItemRequest) -> None:
        super().update_workout_item(item_id, item)
        if item_id == self._stale_item_id:
            msg = "missing"
            raise TrueCoachAPIError(msg, status_code=404, url=f"workout_items/{item_id}")

    def get_recent_workout(
        self,
        workout_id: int,
    ) -> tuple[TrueCoachWorkoutPayload, list[TrueCoachWorkoutItemPayload]] | None:
        self.refresh_requests.append(workout_id)
        return (
            _true_coach_workout_payload(workout_id, [9201, 9102, 9103, 9104, 9105]),
            [
                self._replacement_item,
                _true_coach_workout_item_payload(
                    item_id=9102,
                    name="Tempo Balance",
                    position=2,
                ),
                _true_coach_workout_item_payload(
                    item_id=9103,
                    name="Chest Supported Row Warmup",
                    position=3,
                ),
                _true_coach_workout_item_payload(
                    item_id=9104,
                    name="Chest Supported Row Main",
                    position=4,
                ),
                _true_coach_workout_item_payload(
                    item_id=9105,
                    name="DB Curl",
                    position=5,
                ),
            ],
        )


def _true_coach_workout_payload(
    workout_id: int,
    workout_item_ids: list[int],
) -> TrueCoachWorkoutPayload:
    return TrueCoachWorkoutPayload(
        id=workout_id,
        due="2026-05-18",
        short_description="",
        created_at="2026-05-18T00:00:00.000000Z",
        updated_at="2026-05-18T00:10:00.000000Z",
        title="Upper Result",
        state="pending",
        rest_day=False,
        rest_day_instructions="",
        warmup=None,
        warmup_selected_exercises=[],
        cooldown_selected_exercises=[],
        cooldown=None,
        position=None,
        order=1,
        uuid=f"uuid-{workout_id}",
        program_name=None,
        hidden=False,
        edit_client_workout=True,
        client_id=2876143,
        comment_ids=[],
        note_id=None,
        program_id=None,
        workout_item_ids=workout_item_ids,
    )


def _true_coach_workout_item_payload(
    *,
    item_id: int,
    name: str,
    position: int,
) -> TrueCoachWorkoutItemPayload:
    exercise_ids = {
        "Bench Press": 701,
        "Tempo Balance": 702,
        "Chest Supported Row Warmup": 703,
        "Chest Supported Row Main": 703,
        "DB Curl": 704,
    }
    return TrueCoachWorkoutItemPayload(
        id=item_id,
        workout_id=9001,
        name=name,
        info="2 x 8" if name == "Bench Press" else "",
        result="",
        is_circuit=False,
        state="pending",
        selected_exercises=[],
        linked=False,
        position=position,
        assessment_id=None,
        created_at="2026-05-18T00:00:00.000000Z",
        attachments=[],
        exercise_id=exercise_ids[name],
        request_video=False,
    )


def _replace_row_work_with_repeated_warmup_and_main(store: Store, *, ambiguous: bool) -> None:
    with store.unit_of_work() as uow:
        row_item = uow.session.query(HevyAppWorkoutItem).filter_by(index=2).one()
        for set_ in list(row_item.sets):
            uow.session.delete(set_)
        uow.session.flush()
        row_item.index = 2
        uow.session.add(
            HevyAppWorkoutItem(
                workout_id="hevy-result-1",
                index=4,
                name="Chest Supported Row",
                notes="",
                superset_id=None,
                exercise_id="hevy-row",
            )
        )
        uow.session.flush()
        row_items = (
            uow.session.query(HevyAppWorkoutItem)
            .filter_by(workout_id="hevy-result-1", exercise_id="hevy-row")
            .order_by(HevyAppWorkoutItem.index)
            .all()
        )
        warmup_reps = 10 if ambiguous else 12
        for row in (
            HevyAppSets(
                workout_item_id=row_items[0].id,
                index=0,
                type="normal",
                weight_kg=35.0,
                reps=warmup_reps,
            ),
            HevyAppSets(
                workout_item_id=row_items[1].id,
                index=0,
                type="normal",
                weight_kg=55.0,
                reps=10,
            ),
            HevyAppSets(
                workout_item_id=row_items[1].id,
                index=1,
                type="normal",
                weight_kg=55.0,
                reps=10,
            ),
        ):
            uow.session.add(row)


def _seed_result_review_workout(store: Store) -> None:
    now = datetime(2026, 5, 18, tzinfo=UTC)
    with store.unit_of_work() as uow:
        for row in (
            HevyAppExercise(
                id="hevy-bench",
                name="Bench Press",
                type="weight_reps",
                equipment="barbell",
                default=True,
            ),
            HevyAppExercise(
                id="hevy-custom",
                name="Tempo Balance",
                type="custom_metric",
                equipment="bodyweight",
                default=True,
            ),
            HevyAppExercise(
                id="hevy-row",
                name="Chest Supported Row",
                type="weight_reps",
                equipment="machine",
                default=True,
            ),
            HevyAppExercise(
                id="hevy-curl",
                name="DB Curl",
                type="weight_reps",
                equipment="dumbbell",
                default=True,
            ),
        ):
            uow.session.add(row)
        for row in (
            TrueCoachExercise(id=701, name="Bench Press", default=False),
            TrueCoachExercise(id=702, name="Tempo Balance", default=False),
            TrueCoachExercise(id=703, name="Chest Supported Row", default=False),
            TrueCoachExercise(id=704, name="DB Curl", default=False),
        ):
            uow.session.add(row)
        for row in (
            TrackerExercise(name="Bench Press", hevy_app_id="hevy-bench", true_coach_id=701),
            TrackerExercise(name="Tempo Balance", hevy_app_id="hevy-custom", true_coach_id=702),
            TrackerExercise(name="Chest Supported Row", hevy_app_id="hevy-row", true_coach_id=703),
            TrackerExercise(name="DB Curl", hevy_app_id="hevy-curl", true_coach_id=704),
        ):
            uow.session.add(row)
        uow.session.add(
            TrueCoachWorkout(
                id=9001,
                title="Upper Result",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(
            HevyAppWorkout(
                id="hevy-result-1",
                title="Upper Result",
                description="",
                start_time=now,
                end_time=now,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.flush()
        tracker_exercises = {
            exercise.name: exercise
            for exercise in uow.session.query(TrackerExercise).order_by(TrackerExercise.id)
        }
        uow.session.add(
            TrackerWorkout(
                title="Upper Result",
                description="",
                start_date=now,
                end_date=now,
                hevy_app_id="hevy-result-1",
                true_coach_id=9001,
            )
        )
        uow.session.flush()
        tracker_workout = uow.session.query(TrackerWorkout).filter_by(true_coach_id=9001).one()
        for row in (
            TrueCoachWorkoutItem(
                id=9101,
                workout_id=9001,
                name="Bench Press",
                info="2 x 8",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=701,
                assessment_id=None,
            ),
            TrueCoachWorkoutItem(
                id=9102,
                workout_id=9001,
                name="Tempo Balance",
                info="2 sets",
                comment="",
                is_circuit=False,
                state="pending",
                position=2,
                exercise_id=702,
                assessment_id=None,
            ),
            TrueCoachWorkoutItem(
                id=9103,
                workout_id=9001,
                name="Chest Supported Row Warmup",
                info="1 x 12",
                comment="",
                is_circuit=False,
                state="pending",
                position=3,
                exercise_id=703,
                assessment_id=None,
            ),
            TrueCoachWorkoutItem(
                id=9104,
                workout_id=9001,
                name="Chest Supported Row Main",
                info="2 x 10",
                comment="",
                is_circuit=False,
                state="pending",
                position=4,
                exercise_id=703,
                assessment_id=None,
            ),
            TrueCoachWorkoutItem(
                id=9105,
                workout_id=9001,
                name="DB Curl",
                info="2 x 12",
                comment="",
                is_circuit=False,
                state="pending",
                position=5,
                exercise_id=704,
                assessment_id=None,
            ),
        ):
            uow.session.add(row)
        for row in (
            HevyAppWorkoutItem(
                workout_id="hevy-result-1",
                index=0,
                name="Bench Press",
                notes="",
                superset_id=None,
                exercise_id="hevy-bench",
            ),
            HevyAppWorkoutItem(
                workout_id="hevy-result-1",
                index=1,
                name="Tempo Balance",
                notes="",
                superset_id=None,
                exercise_id="hevy-custom",
            ),
            HevyAppWorkoutItem(
                workout_id="hevy-result-1",
                index=2,
                name="Chest Supported Row",
                notes="",
                superset_id=None,
                exercise_id="hevy-row",
            ),
            HevyAppWorkoutItem(
                workout_id="hevy-result-1",
                index=3,
                name="DB Curl",
                notes="",
                superset_id=None,
                exercise_id="hevy-curl",
            ),
        ):
            uow.session.add(row)
        uow.session.flush()
        hevy_items = {
            item.index: item
            for item in uow.session.query(HevyAppWorkoutItem).order_by(HevyAppWorkoutItem.index)
        }
        for row in (
            HevyAppSets(
                workout_item_id=hevy_items[0].id,
                index=0,
                type="normal",
                weight_kg=80.0,
                reps=8,
            ),
            HevyAppSets(
                workout_item_id=hevy_items[0].id,
                index=1,
                type="normal",
                weight_kg=80.0,
                reps=7,
            ),
            HevyAppSets(workout_item_id=hevy_items[1].id, index=0, type="normal", reps=1),
            HevyAppSets(
                workout_item_id=hevy_items[2].id,
                index=0,
                type="normal",
                weight_kg=55.0,
                reps=10,
            ),
            HevyAppSets(
                workout_item_id=hevy_items[3].id,
                index=0,
                type="normal",
                weight_kg=14.0,
                reps=12,
            ),
        ):
            uow.session.add(row)
        for row in (
            TrackerWorkoutItem(
                workout_id=tracker_workout.id,
                position=1,
                exercise_id=tracker_exercises["Bench Press"].id,
                hevy_app_id=hevy_items[0].id,
                true_coach_id=9101,
                rest=90,
            ),
            TrackerWorkoutItem(
                workout_id=tracker_workout.id,
                position=2,
                exercise_id=tracker_exercises["Tempo Balance"].id,
                hevy_app_id=hevy_items[1].id,
                true_coach_id=9102,
                rest=90,
            ),
            TrackerWorkoutItem(
                workout_id=tracker_workout.id,
                position=3,
                exercise_id=tracker_exercises["Chest Supported Row"].id,
                hevy_app_id=None,
                true_coach_id=9103,
                rest=90,
            ),
            TrackerWorkoutItem(
                workout_id=tracker_workout.id,
                position=4,
                exercise_id=tracker_exercises["Chest Supported Row"].id,
                hevy_app_id=None,
                true_coach_id=9104,
                rest=90,
            ),
        ):
            uow.session.add(row)
