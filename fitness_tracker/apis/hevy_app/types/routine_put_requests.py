"""Routine PUT request models for the Hevy API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PutRoutinesRepRange(BaseModel):
    """Rep range for a set in a routine update."""

    start: int | None = None
    end: int | None = None


class PutRoutinesRequestSet(BaseModel):
    """Set row when updating a routine via PUT."""

    type: Literal["normal", "warmup", "failure", "dropset"] = "normal"
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    custom_metric: float | None = None
    rep_range: PutRoutinesRepRange | None = None


class PutRoutinesRequestExercise(BaseModel):
    """Exercise block when updating a routine."""

    exercise_template_id: str
    superset_id: int | None = None
    rest_seconds: int | None = None
    notes: str | None = None
    sets: list[PutRoutinesRequestSet]


class PutRoutinesRequest(BaseModel):
    """Top-level routine fields for an update."""

    title: str
    notes: str | None = None
    exercises: list[PutRoutinesRequestExercise]


class PutRoutinesRequestBody(BaseModel):
    """Wrapper object expected by ``PUT /v1/routines/{routineId}``."""

    routine: PutRoutinesRequest
