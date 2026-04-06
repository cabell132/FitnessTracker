"""Types describing a full :meth:`~fitness_tracker.sync._service.SyncService.run` result."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SyncRunResult:
    """Immutable summary of a sync run."""

    hevy_event_count: int = 0
    hevy_routines_deleted: int = 0
    true_coach_workouts_synced: int = 0
    duration_ms: float = 0.0
    outcome: str = "success"
