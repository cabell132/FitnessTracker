"""Exercise block model for Hevy API payloads."""

from __future__ import annotations

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.set import Set


class Exercise(BaseModel):
    """Exercise block with nested sets inside a workout or routine."""

    index: int
    title: str
    notes: str | None = None
    exercise_template_id: str
    superset_id: bool | int | None = None
    sets: list[Set]
