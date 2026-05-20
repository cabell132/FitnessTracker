"""Tests for :meth:`~fitness_tracker.sync._service.SyncService.run` orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fitness_tracker.apis.hevy_app.types import UpdatedWorkout, Workout
from fitness_tracker.sync._deps import SyncDeps
from fitness_tracker.sync._service import SyncService
from fitness_tracker.sync.adapters.file_checkpoint_store import (
    FileCheckpointStore,
    HEVY_CHECKPOINT_KEY,
    InMemoryCheckpointStore,
)

_SENTINEL = datetime(1970, 1, 1, tzinfo=UTC)


def _deps_with_mocks(
    store,
    checkpoints: InMemoryCheckpointStore | FileCheckpointStore,
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
    monkeypatch.setattr(svc, "get_due_workouts", list)

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
    monkeypatch.setattr(
        svc,
        "clear_hevy_routines",
        lambda **_: order.append("clear") or 0,
    )
    monkeypatch.setattr(svc, "get_due_workouts", lambda: order.append("due") or [])
    monkeypatch.setattr(
        svc,
        "create_hevy_routine",
        lambda wid: order.append(f"routine:{wid}") or None,
    )

    svc.run()

    assert order == [
        "apple",
        "tc-fetch",
        "hevy",
        "assessments",
        "clear",
        "tc-fetch",
        "due",
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
    monkeypatch.setattr(svc, "get_due_workouts", list)

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
    monkeypatch.setattr(svc, "get_due_workouts", list)

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


def test_should_populate_sync_run_result_counters_from_run(
    store,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Summary counts reflect Hevy events, deletions, and due workouts."""
    checkpoints = InMemoryCheckpointStore()
    deps = _deps_with_mocks(store, checkpoints)
    svc = SyncService(deps)
    fake_events = [object(), object()]

    monkeypatch.setattr(svc, "sync_apple_health", lambda: None)
    monkeypatch.setattr(svc, "sync_hevy_workouts", lambda since: fake_events)
    monkeypatch.setattr(svc, "sync_assessments", lambda: None)
    monkeypatch.setattr(svc, "clear_hevy_routines", lambda **_: 3)
    monkeypatch.setattr(svc, "fetch_recent_true_coach_workouts", lambda: None)
    monkeypatch.setattr(
        svc,
        "get_due_workouts",
        lambda: [SimpleNamespace(id=7), SimpleNamespace(id=8)],
    )
    created: list[int] = []
    monkeypatch.setattr(
        svc,
        "create_hevy_routine",
        lambda wid: created.append(wid),
    )

    result = svc.run(now=datetime(2026, 1, 1, tzinfo=UTC))

    assert result.hevy_event_count == 2
    assert result.hevy_routines_deleted == 3
    assert result.true_coach_workouts_synced == 2
    assert result.outcome == "success"
    assert created == [7, 8]
    assert result.duration_ms >= 0.0


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
    monkeypatch.setattr(svc, "get_due_workouts", list)

    svc.run(now=fixed)
    assert checkpoints.read(HEVY_CHECKPOINT_KEY, _SENTINEL) == fixed
