"""Workout request models for the Hevy API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PostWorkoutsRequestSet(BaseModel):
    """Set row when creating a workout via POST."""

    type: Literal["normal", "warmup", "failure", "dropset"] = "normal"
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    rpe: float | None = None


class PostWorkoutsRequestExercise(BaseModel):
    """Exercise block when creating a workout."""

    exercise_template_id: str
    notes: str | None = None
    superset_id: int | None = None
    sets: list[PostWorkoutsRequestSet]


class PostWorkoutsRequest(BaseModel):
    """Top-level workout fields for creation."""

    title: str
    description: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    is_private: bool = False
    exercises: list[PostWorkoutsRequestExercise]
