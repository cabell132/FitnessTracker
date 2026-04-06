"""Routine POST request/response models for the Hevy API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.routine import Routine


class PostRoutinesRequestSet(BaseModel):
    """Set row when creating a routine via POST."""

    type: Literal["normal", "warmup", "failure", "dropset"] = "normal"
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None


class PostRoutinesRequestExercise(BaseModel):
    """Exercise block when creating a routine."""

    notes: str
    exercise_template_id: str
    superset_id: int | None = None
    rest_seconds: int | None = None
    sets: list[PostRoutinesRequestSet]


class PostRoutinesRequest(BaseModel):
    """Top-level routine fields for creation."""

    title: str
    folder_id: str | None = None
    notes: str
    exercises: list[PostRoutinesRequestExercise]


class PostRoutinesRequestBody(BaseModel):
    """Wrapper object expected by the routines POST endpoint."""

    routine: PostRoutinesRequest


class PostRoutinesResponse(BaseModel):
    """Response body after creating a routine."""

    routine: list[Routine]
