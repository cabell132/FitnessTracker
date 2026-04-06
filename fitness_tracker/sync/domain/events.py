"""Sync-layer domain events replacing leaked API DTOs.

Callers pattern-match on :data:`SyncEvent` instead of Hevy API types,
keeping the sync boundary clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WorkoutSynced:
    """A Hevy workout was created or updated in the tracker."""

    hevy_workout_id: str
    title: str
    started_at: datetime
    ended_at: datetime


@dataclass(frozen=True)
class WorkoutDeleted:
    """A Hevy workout was deleted from the tracker."""

    hevy_workout_id: str
    deleted_at: datetime


SyncEvent = WorkoutSynced | WorkoutDeleted
