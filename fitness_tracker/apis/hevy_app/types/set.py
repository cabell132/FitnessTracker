"""Set model for Hevy API payloads."""

from __future__ import annotations

from pydantic import BaseModel


class Set(BaseModel):
    """One logged set inside a workout or routine block."""

    index: int
    type: str
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    rpe: int | None = None
