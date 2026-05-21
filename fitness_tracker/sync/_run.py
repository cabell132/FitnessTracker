"""Types describing a full :meth:`~fitness_tracker.sync._service.SyncService.run` result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


type RoutineReplacementStatus = Literal[
    "applied",
    "review_required",
    "no_due_workouts",
    "failed",
]


@dataclass(frozen=True)
class SyncRunResult:
    """Immutable summary of a sync run."""

    hevy_event_count: int = 0
    routine_replacement_status: RoutineReplacementStatus = "no_due_workouts"
    routine_replacement_due_workout_count: int = 0
    routine_replacement_safe_plan_count: int = 0
    routine_replacement_review_required_plan_count: int = 0
    routine_replacement_review_artifact_count: int = 0
    routine_replacement_review_artifact_dirs: tuple[str, ...] = ()
    routine_replacement_error: str | None = None
    hevy_routines_created: int = 0
    hevy_routines_deleted: int = 0
    true_coach_workouts_synced: int = 0
    duration_ms: float = 0.0
    outcome: str = "success"
