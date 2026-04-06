"""Exercise history models for the Hevy API."""

from __future__ import annotations

from pydantic import BaseModel


class ExerciseHistoryEntry(BaseModel):
    """Single set-level history entry for an exercise template."""

    workout_id: str
    workout_title: str
    workout_start_time: str
    workout_end_time: str
    exercise_template_id: str
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    rpe: float | None = None
    custom_metric: float | None = None
    set_type: str


class ExerciseHistoryResponse(BaseModel):
    """Response from ``GET /v1/exercise_history/{exerciseTemplateId}``."""

    exercise_history: list[ExerciseHistoryEntry]
