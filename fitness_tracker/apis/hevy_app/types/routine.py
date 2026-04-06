"""Routine models for the Hevy API."""

from __future__ import annotations

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.exercise import Exercise


class Routine(BaseModel):
    """Saved routine (template) returned by the routines API."""

    id: str
    title: str
    updated_at: str
    created_at: str
    exercises: list[Exercise]


class RoutineResponse(BaseModel):
    """Paginated routines list."""

    page: int
    page_count: int
    routines: list[Routine]
