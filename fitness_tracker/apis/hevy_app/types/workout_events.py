"""Workout event models for incremental sync."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fitness_tracker.apis.hevy_app.types.workout import Workout


class UpdatedWorkout(BaseModel):
    """Workout change event from the events feed."""

    type: str
    workout: Workout


class DeletedWorkout(BaseModel):
    """Deletion event from the workout events feed."""

    type: str
    id: str
    deleted_at: str


class PaginatedWorkoutEvents(BaseModel):
    """Paged workout events used for incremental sync."""

    page: int
    page_count: int
    events: list[UpdatedWorkout | DeletedWorkout] = Field(default_factory=list)
