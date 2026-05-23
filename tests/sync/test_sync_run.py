"""Tests for :meth:`~fitness_tracker.sync._service.SyncService.run` orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fitness_tracker.apis.hevy_app.types import UpdatedWorkout, Workout
from fitness_tracker.database.models.hevy_app import HevyAppExercise
from fitness_tracker.database.models.tracker import Exercise as TrackerExercise
from fitness_tracker.database.models.true_coach import (
    TrueCoachExercise,
    TrueCoachWorkout,
    TrueCoachWorkoutItem,
)
from fitness_tracker.sync._deps import SyncDeps
from fitness_tracker.sync._service import SyncService
from fitness_tracker.sync.adapters.file_checkpoint_store import (
    FileCheckpointStore,
    HEVY_CHECKPOINT_KEY,
    InMemoryCheckpointStore,
)
from fitness_tracker.sync.true_coach_hevy.sync import (
    LEGACY_DIRECT_ROUTINE_CREATION_ERROR,
    TrueCoachToHevySyncronizer,
)
from fitness_tracker.sync_review.true_coach_to_hevy import (
    ReviewBundle,
    RoutineReplacementBatchResult,
)

_SENTINEL = datetime(1970, 1, 1, tzinfo=UTC)


def _deps_with_mocks(
    store,
    checkpoints: InMemoryCheckpointStore | FileCheckpointStore,
    output_root: Path | None = None,
) -> SyncDeps:
    """Build :class:`SyncDeps` with non-persistent clients for isolation.

    Args:
        store: Database store under test.
        checkpoints: Checkpoint backing store.

    Returns:
        SyncDeps: Wired dependency bundle.
    """
    return SyncDeps(
        store=store,
        hevy=MagicMock(),
        true_coach=MagicMock(),
        llm=MagicMock(),
        dbx=MagicMock(),
        checkpoints=checkpoints,
        routine_review_output_root=output_root or Path("reports"),
    )


def _hevy_workout(workout_id: str) -> Workout:
    return Workout(
        id=workout_id,
        title="TrueCoach 123",
        description="",
        start_time="2026-05-20T10:00:00+00:00",
        end_time="2026-05-20T11:00:00+00:00",
        updated_at="2026-05-20T11:05:00+00:00",
        created_at="2026-05-20T10:00:00+00:00",
        exercises=[],
    )


def test_should_update_hevy_checkpoint_after_run_when_using_in_memory_store(
    store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checkpoint for Hevy is written to ``now`` after a successful Hevy step."""
    checkpoints = InMemoryCheckpointStore(
        {HEVY_CHECKPOINT_KEY: datetime(2026, 4, 1, tzinfo=UTC)},
    )
    deps = _deps_with_mocks(store, checkpoints)
    svc = SyncService(deps)
    monkeypatch.setattr(svc, "sync_apple_health", lambda: None)
    monkeypatch.setattr(svc, "sync_hevy_workouts", lambda since: [])
    monkeypatch.setattr(svc, "sync_assessments", lambda: None)
    monkeypatch.setattr(svc, "clear_hevy_routines", lambda **_: 0)
    monkeypatch.setattr(svc, "fetch_recent_true_coach_workouts", lambda: None)
    monkeypatch.setattr(svc, "get_due_workouts", lambda **_: [])

    fixed_now = datetime(2026, 4, 6, 12, 0, tzinfo=UTC)
    result = svc.run(now=fixed_now)

    assert checkpoints.read(HEVY_CHECKPOINT_KEY, _SENTINEL) == fixed_now
    assert result.outcome == "success"
    assert result.hevy_event_count == 0


def test_should_execute_sync_steps_in_declared_order(
    store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full run invokes each platform step in the pipeline order."""
    order: list[str] = []
    checkpoints = InMemoryCheckpointStore()
    deps = _deps_with_mocks(store, checkpoints)
    svc = SyncService(deps)

    monkeypatch.setattr(svc, "sync_apple_health", lambda: order.append("apple") or None)
    monkeypatch.setattr(
        svc,
        "fetch_recent_true_coach_workouts",
        lambda: order.append("tc-fetch") or None,
    )
    monkeypatch.setattr(
        svc,
        "sync_hevy_workouts",
        lambda since: order.append("hevy") or [],
    )
    monkeypatch.setattr(svc, "sync_assessments", lambda: order.append("assessments") or None)
    monkeypatch.setattr(svc, "get_due_workouts", lambda **_: order.append("due") or [])
    monkeypatch.setattr(
        svc,
        "replace_due_hevy_routines",
        lambda workouts: order.append("routine-batch") or _routine_batch_result(),
    )

    svc.run()

    assert order == [
        "apple",
        "tc-fetch",
        "hevy",
        "assessments",
        "tc-fetch",
        "due",
        "routine-batch",
    ]


def test_should_pass_default_since_when_hevy_checkpoint_missing(
    store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing Hevy checkpoint uses the configured lower bound, not crash."""
    captured: dict[str, datetime] = {}
    checkpoints = InMemoryCheckpointStore()
    deps = _deps_with_mocks(store, checkpoints)
    svc = SyncService(deps)

    def capture_since(since: datetime) -> list:
        captured["since"] = since
        return []

    monkeypatch.setattr(svc, "sync_apple_health", lambda: None)
    monkeypatch.setattr(svc, "sync_hevy_workouts", capture_since)
    monkeypatch.setattr(svc, "sync_assessments", lambda: None)
    monkeypatch.setattr(svc, "clear_hevy_routines", lambda **_: 0)
    monkeypatch.setattr(svc, "fetch_recent_true_coach_workouts", lambda: None)
    monkeypatch.setattr(svc, "get_due_workouts", lambda **_: [])

    svc.run()

    assert captured["since"] == datetime(2025, 1, 1, tzinfo=UTC)


def test_should_sync_true_coach_workouts_only_when_fetch_returns_payload(
    store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conditional True Coach import runs only when fetch is non-null."""
    tc_called: list[bool] = []
    checkpoints = InMemoryCheckpointStore()
    deps = _deps_with_mocks(store, checkpoints)
    svc = SyncService(deps)

    monkeypatch.setattr(svc, "sync_apple_health", lambda: None)
    monkeypatch.setattr(svc, "sync_hevy_workouts", lambda since: [])
    monkeypatch.setattr(svc, "sync_assessments", lambda: None)
    monkeypatch.setattr(svc, "clear_hevy_routines", lambda **_: 0)
    monkeypatch.setattr(svc, "fetch_recent_true_coach_workouts", lambda: SimpleNamespace())
    monkeypatch.setattr(
        svc,
        "sync_true_coach_workouts",
        lambda res: tc_called.append(True),
    )
    monkeypatch.setattr(svc, "get_due_workouts", lambda **_: [])

    svc.run()
    assert tc_called == [True, True]


def test_hevy_workout_updates_use_result_sync_workflow(
    store,
) -> None:
    """Updated Hevy Workouts cascade through the strict Result sync workflow."""
    checkpoints = InMemoryCheckpointStore()
    deps = _deps_with_mocks(store, checkpoints)
    svc = SyncService(deps)
    event = UpdatedWorkout(type="updated", workout=_hevy_workout("hevy-workout-1"))

    svc._hevy_to_tracker.sync_workouts = MagicMock(return_value=[event])
    svc._hevy_result_sync_workflow.sync_one = MagicMock()

    result = svc.sync_hevy_workouts(since=datetime(2026, 5, 20, tzinfo=UTC))

    assert result == [event]
    svc._hevy_result_sync_workflow.sync_one.assert_called_once_with(
        "hevy-workout-1",
        workout_item_writer=svc._true_coach_workout_item_writer,
    )


def test_create_hevy_routine_uses_strict_review_apply_workflow(
    store,
    tmp_path: Path,
) -> None:
    """Single Routine creation uses the review/apply path, not legacy LLM parsing."""
    _seed_clean_due_workout(store)
    deps = _deps_with_mocks(
        store,
        InMemoryCheckpointStore(),
        output_root=tmp_path / "reports",
    )
    deps.hevy.routines.create.return_value = None
    svc = SyncService(deps)

    svc.create_hevy_routine(47)

    deps.hevy.routines.create.assert_called_once()
    deps.llm.parse_the_sets.assert_not_called()
    request = deps.hevy.routines.create.call_args.args[0]
    assert request.routine.notes == "TrueCoachWorkoutId: 47\nRoutineBatch: truecoach-to-hevy"
    _assert_routine_plan_safety(tmp_path, workout_id=47, auto_safe=True)
    assert (
        tmp_path / "reports" / "sync-review" / "truecoach-to-hevy" / "47" / "hevy-request.json"
    ).exists()


def test_legacy_direct_routine_creation_raises_deprecation_error(store) -> None:
    """Retired direct Routine creation cannot mutate Hevy outside the workflow."""
    syncer = TrueCoachToHevySyncronizer(
        store=store,
        source=MagicMock(),
        target=MagicMock(),
        llm=MagicMock(),
    )

    with pytest.raises(RuntimeError, match=LEGACY_DIRECT_ROUTINE_CREATION_ERROR):
        syncer.sync_workout(47)


def test_should_populate_sync_run_result_counters_from_run(
    store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Summary counts reflect Hevy events and applied Routine replacement results."""
    checkpoints = InMemoryCheckpointStore()
    deps = _deps_with_mocks(store, checkpoints)
    svc = SyncService(deps)
    fake_events = [object(), object()]

    monkeypatch.setattr(svc, "sync_apple_health", lambda: None)
    monkeypatch.setattr(svc, "sync_hevy_workouts", lambda since: fake_events)
    monkeypatch.setattr(svc, "sync_assessments", lambda: None)
    monkeypatch.setattr(svc, "fetch_recent_true_coach_workouts", lambda: None)
    due_workouts = [SimpleNamespace(id=7), SimpleNamespace(id=8)]
    monkeypatch.setattr(
        svc,
        "get_due_workouts",
        lambda **_: due_workouts,
    )
    batched: list[list[int]] = []
    monkeypatch.setattr(
        svc,
        "replace_due_hevy_routines",
        lambda workouts: batched.append([workout.id for workout in workouts])
        or _applied_routine_batch_result(),
    )

    result = svc.run(now=datetime(2026, 1, 1, tzinfo=UTC))

    assert {
        "hevy_event_count": result.hevy_event_count,
        "routine_replacement_status": result.routine_replacement_status,
        "routine_replacement_due_workout_count": result.routine_replacement_due_workout_count,
        "routine_replacement_safe_plan_count": result.routine_replacement_safe_plan_count,
        "routine_replacement_review_required_plan_count": (
            result.routine_replacement_review_required_plan_count
        ),
        "hevy_routines_created": result.hevy_routines_created,
        "hevy_routines_deleted": result.hevy_routines_deleted,
        "routine_replacement_review_artifact_count": (
            result.routine_replacement_review_artifact_count
        ),
        "true_coach_workouts_synced": result.true_coach_workouts_synced,
        "outcome": result.outcome,
    } == {
        "hevy_event_count": 2,
        "routine_replacement_status": "applied",
        "routine_replacement_due_workout_count": 2,
        "routine_replacement_safe_plan_count": 2,
        "routine_replacement_review_required_plan_count": 0,
        "hevy_routines_created": 2,
        "hevy_routines_deleted": 3,
        "routine_replacement_review_artifact_count": 2,
        "true_coach_workouts_synced": 0,
        "outcome": "success",
    }
    assert result.routine_replacement_review_artifact_dirs == (
        "reports/sync-review/truecoach-to-hevy/7",
        "reports/sync-review/truecoach-to-hevy/8",
    )
    assert batched == [[7, 8]]
    assert result.duration_ms >= 0.0


def test_run_blocks_due_routine_replacement_batch_before_deleting_routines(
    store,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A review-required due batch writes every review and leaves Hevy untouched."""
    _seed_clean_due_workout(store)
    _seed_unsafe_due_workout(store)
    checkpoints = InMemoryCheckpointStore()
    deps = _deps_with_mocks(store, checkpoints, output_root=tmp_path / "reports")
    svc = SyncService(deps)

    _disable_non_routine_sync_steps(svc, monkeypatch)

    result = svc.run(now=datetime(2026, 5, 21, tzinfo=UTC))

    assert result.routine_replacement_status == "review_required"
    assert result.routine_replacement_due_workout_count == 2
    assert result.routine_replacement_safe_plan_count == 1
    assert result.routine_replacement_review_required_plan_count == 1
    assert result.routine_replacement_review_artifact_count == 2
    assert result.hevy_routines_created == 0
    assert result.hevy_routines_deleted == 0
    deps.hevy.routines.get.assert_not_called()
    deps.hevy.routines.create.assert_not_called()
    _assert_routine_plan_safety(tmp_path, workout_id=47, auto_safe=True)
    _assert_routine_plan_safety(tmp_path, workout_id=42, auto_safe=False)
    assert result.true_coach_workouts_synced == 0


def test_run_skips_routine_deletion_when_no_workouts_are_due(
    store,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty due batch is a no-op for the Hevy Routine menu."""
    checkpoints = InMemoryCheckpointStore()
    deps = _deps_with_mocks(store, checkpoints, output_root=tmp_path / "reports")
    svc = SyncService(deps)

    _disable_non_routine_sync_steps(svc, monkeypatch)

    result = svc.run(now=datetime(2026, 5, 21, tzinfo=UTC))

    assert result.routine_replacement_status == "no_due_workouts"
    assert result.routine_replacement_due_workout_count == 0
    assert result.routine_replacement_safe_plan_count == 0
    assert result.routine_replacement_review_required_plan_count == 0
    assert result.routine_replacement_review_artifact_count == 0
    assert result.hevy_routines_deleted == 0
    assert result.true_coach_workouts_synced == 0
    deps.hevy.routines.get.assert_not_called()
    deps.hevy.routines.delete.assert_not_called()
    deps.hevy.routines.create.assert_not_called()
    assert not (tmp_path / "reports" / "sync-review" / "truecoach-to-hevy").exists()


def test_run_reports_failed_due_routine_replacement_batch(
    store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routine replacement failures are visible in the sync run result."""
    checkpoints = InMemoryCheckpointStore()
    deps = _deps_with_mocks(store, checkpoints)
    svc = SyncService(deps)

    _disable_non_routine_sync_steps(svc, monkeypatch)
    monkeypatch.setattr(svc, "get_due_workouts", lambda **_: [SimpleNamespace(id=7)])

    def fail_replacement(workouts):
        msg = "routine API failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(svc, "replace_due_hevy_routines", fail_replacement)

    result = svc.run(now=datetime(2026, 5, 21, tzinfo=UTC))

    assert result.outcome == "failed"
    assert result.routine_replacement_status == "failed"
    assert result.routine_replacement_due_workout_count == 1
    assert result.routine_replacement_error == "routine API failed"
    assert result.hevy_routines_created == 0
    assert result.hevy_routines_deleted == 0
    assert result.true_coach_workouts_synced == 0


def test_should_round_trip_multiple_keys_in_file_checkpoint_store(tmp_path) -> None:
    """JSON backing file merges keys and survives missing file on first read."""
    path = tmp_path / "sync_checkpoints.json"
    cp = FileCheckpointStore(path=path)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 2, 1, tzinfo=UTC)

    assert cp.read("hevy", t0) == t0

    cp.write("hevy", t1)
    cp.write("other", t0)

    store2 = FileCheckpointStore(path=path)
    assert store2.read("hevy", _SENTINEL) == t1
    assert store2.read("other", _SENTINEL) == t0


def test_should_ignore_corrupt_json_file_when_reading_checkpoint(tmp_path) -> None:
    """Corrupt checkpoint file yields the caller default."""
    path = tmp_path / "bad.json"
    path.write_text("not-json{{{", encoding="utf-8")
    cp = FileCheckpointStore(path=path)
    fallback = datetime(2020, 1, 1, tzinfo=UTC)
    assert cp.read("hevy", fallback) is fallback


def test_should_read_legacy_hevy_last_sync_when_json_missing(tmp_path) -> None:
    """Migrates ``hevy_last_sync.txt`` when the new JSON store does not exist."""
    legacy = tmp_path / "hevy_last_sync.txt"
    legacy.write_text("2026-03-15T08:00:00+00:00", encoding="utf-8")
    json_path = tmp_path / "sync_checkpoints.json"
    cp = FileCheckpointStore(path=json_path)
    got = cp.read(HEVY_CHECKPOINT_KEY, datetime(2000, 1, 1, tzinfo=UTC))
    assert got == datetime(2026, 3, 15, 8, 0, tzinfo=UTC)


def test_should_use_fixed_now_for_hevy_checkpoint_write(
    store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``run(now=...)`` writes the supplied instant to the checkpoint."""
    checkpoints = InMemoryCheckpointStore()
    deps = _deps_with_mocks(store, checkpoints)
    svc = SyncService(deps)
    fixed = datetime(2030, 6, 1, 15, 30, tzinfo=UTC)

    monkeypatch.setattr(svc, "sync_apple_health", lambda: None)
    monkeypatch.setattr(svc, "sync_hevy_workouts", lambda since: [])
    monkeypatch.setattr(svc, "sync_assessments", lambda: None)
    monkeypatch.setattr(svc, "clear_hevy_routines", lambda **_: 0)
    monkeypatch.setattr(svc, "fetch_recent_true_coach_workouts", lambda: None)
    monkeypatch.setattr(svc, "get_due_workouts", lambda **_: [])

    svc.run(now=fixed)
    assert checkpoints.read(HEVY_CHECKPOINT_KEY, _SENTINEL) == fixed


def _applied_routine_batch_result() -> RoutineReplacementBatchResult:
    return _routine_batch_result(
        status="applied",
        review_bundles=[
            _review_bundle(7),
            _review_bundle(8),
        ],
        apply_results=[object(), object()],
        deleted_routine_count=3,
        created_routine_ids=["routine-7", "routine-8"],
    )


def _routine_batch_result(**overrides) -> RoutineReplacementBatchResult:
    defaults = {
        "status": "no_due_workouts",
        "review_bundles": [],
        "apply_results": [],
    }
    defaults.update(overrides)
    return RoutineReplacementBatchResult(**defaults)


def _review_bundle(workout_id: int) -> ReviewBundle:
    directory = Path("reports/sync-review/truecoach-to-hevy") / str(workout_id)
    return ReviewBundle(
        directory=directory,
        report_path=directory / "report.md",
        plan_path=directory / "plan.json",
    )


def _disable_non_routine_sync_steps(
    svc: SyncService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc, "sync_apple_health", lambda: None)
    monkeypatch.setattr(svc, "sync_hevy_workouts", lambda since: [])
    monkeypatch.setattr(svc, "sync_assessments", lambda: None)
    monkeypatch.setattr(svc, "fetch_recent_true_coach_workouts", lambda: None)


def _assert_routine_plan_safety(
    tmp_path: Path,
    *,
    workout_id: int,
    auto_safe: bool,
) -> None:
    plan_path = (
        tmp_path / "reports" / "sync-review" / "truecoach-to-hevy" / str(workout_id) / "plan.json"
    )
    assert plan_path.exists()
    assert json.loads(plan_path.read_text())["safety"]["auto_safe"] is auto_safe


def _seed_clean_due_workout(store) -> None:
    workout_id = 47
    item_id = 1007
    exercise_id = 506
    now = datetime(2026, 5, 21, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=workout_id,
                title="Clean Plan",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(TrueCoachExercise(id=exercise_id, name="Push Up", default=False))
        uow.session.add(
            HevyAppExercise(
                id=f"hevy-push-up-{workout_id}",
                name="Push Up",
                type="reps_only",
                equipment="bodyweight",
                default=True,
            )
        )
        uow.session.add(
            TrackerExercise(
                name=f"Push Up {workout_id}",
                hevy_app_id=f"hevy-push-up-{workout_id}",
                true_coach_id=exercise_id,
            )
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=item_id,
                workout_id=workout_id,
                name="Push Up",
                info="3 x 12",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=exercise_id,
                assessment_id=None,
            )
        )


def _seed_unsafe_due_workout(store) -> None:
    now = datetime(2026, 5, 21, tzinfo=UTC)
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=42,
                title="Upper Strength",
                due=now,
                short_description="",
                state="pending",
                rest_day=False,
                created_at=now,
                updated_at=now,
            )
        )
        uow.session.add(
            TrueCoachWorkoutItem(
                id=1002,
                workout_id=42,
                name="Mystery Carry",
                info="3 x 8+8+8",
                comment="",
                is_circuit=False,
                state="pending",
                position=1,
                exercise_id=None,
                assessment_id=None,
            )
        )
