"""Exercise template models for the Hevy API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.common import EQUIPMENT_CATEGORIES, MUSCLE_GROUPS


class ExerciseTemplate(BaseModel):
    """Library exercise definition from the Hevy API."""

    id: str
    title: str
    type: Literal[
        "bodyweight_assisted",
        "bodyweight_weighted",
        "distance_duration",
        "duration",
        "reps_only",
        "short_distance_weight",
        "weight_duration",
        "weight_reps",
    ]
    primary_muscle_group: MUSCLE_GROUPS
    secondary_muscle_groups: list[MUSCLE_GROUPS]
    equipment: EQUIPMENT_CATEGORIES
    is_custom: bool


class ExerciseResponse(BaseModel):
    """Paginated list of exercise templates."""

    page: int
    page_count: int
    exercise_templates: list[ExerciseTemplate]
