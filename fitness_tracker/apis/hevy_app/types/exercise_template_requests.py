"""Request/response models for creating custom exercise templates."""

from __future__ import annotations

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.common import (
    CUSTOM_EXERCISE_TYPES,
    EQUIPMENT_CATEGORIES,
    MUSCLE_GROUPS,
)


class CreateCustomExercise(BaseModel):
    """Inner exercise payload for creating a custom exercise template."""

    title: str
    exercise_type: CUSTOM_EXERCISE_TYPES
    equipment_category: EQUIPMENT_CATEGORIES
    muscle_group: MUSCLE_GROUPS
    other_muscles: list[MUSCLE_GROUPS] = []


class CreateCustomExerciseRequestBody(BaseModel):
    """Wrapper object expected by ``POST /v1/exercise_templates``."""

    exercise: CreateCustomExercise


class CreateCustomExerciseResponse(BaseModel):
    """Response body after creating a custom exercise template."""

    id: int
