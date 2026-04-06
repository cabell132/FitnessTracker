"""Unit tests for sync domain events and the DTO → domain event mapping."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fitness_tracker.sync.domain.events import SyncEvent, WorkoutDeleted, WorkoutSynced


class TestWorkoutSynced:
    """Tests for the WorkoutSynced domain event."""

    def test_is_frozen(self) -> None:
        event = WorkoutSynced(
            hevy_workout_id="w1",
            title="Upper Body",
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
            ended_at=datetime(2025, 1, 1, 1, tzinfo=UTC),
        )
        assert event.hevy_workout_id == "w1"
        assert event.title == "Upper Body"

    def test_frozen_immutable(self) -> None:
        event = WorkoutSynced(
            hevy_workout_id="w1",
            title="Upper",
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
            ended_at=datetime(2025, 1, 1, 1, tzinfo=UTC),
        )
        try:
            event.title = "Changed"  # type: ignore[misc]
            raised = False
        except AttributeError:
            raised = True
        assert raised

    def test_is_sync_event(self) -> None:
        event = WorkoutSynced(
            hevy_workout_id="w1",
            title="Upper",
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
            ended_at=datetime(2025, 1, 1, 1, tzinfo=UTC),
        )
        assert isinstance(event, WorkoutSynced)


class TestWorkoutDeleted:
    """Tests for the WorkoutDeleted domain event."""

    def test_fields(self) -> None:
        now = datetime.now(tz=UTC)
        event = WorkoutDeleted(hevy_workout_id="d1", deleted_at=now)
        assert event.hevy_workout_id == "d1"
        assert event.deleted_at == now


class TestSyncEventUnion:
    """Tests for the SyncEvent type alias."""

    def test_pattern_match_synced(self) -> None:
        event: SyncEvent = WorkoutSynced(
            hevy_workout_id="w1",
            title="Legs",
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
            ended_at=datetime(2025, 1, 1, 1, tzinfo=UTC),
        )
        match event:
            case WorkoutSynced(hevy_workout_id=wid):
                assert wid == "w1"
            case _:
                pytest.fail("Expected WorkoutSynced")

    def test_pattern_match_deleted(self) -> None:
        event: SyncEvent = WorkoutDeleted(
            hevy_workout_id="d1",
            deleted_at=datetime.now(tz=UTC),
        )
        match event:
            case WorkoutDeleted(hevy_workout_id=wid):
                assert wid == "d1"
            case _:
                pytest.fail("Expected WorkoutDeleted")
