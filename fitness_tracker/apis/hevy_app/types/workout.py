"""Workout models for the Hevy API."""

from __future__ import annotations

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.exercise import Exercise


class Workout(BaseModel):
    """Full workout payload including exercise blocks."""

    id: str
    title: str
    description: str | None
    start_time: str
    end_time: str
    updated_at: str
    created_at: str
    exercises: list[Exercise]


class WorkoutResponse(BaseModel):
    """Paginated workouts list."""

    page: int
    page_count: int
    workouts: list[Workout]
