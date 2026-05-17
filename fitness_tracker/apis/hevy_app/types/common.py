"""Shared type aliases and internal base models for Hevy API payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

MUSCLE_GROUPS = Literal[
    "abdominals",
    "abductors",
    "adductors",
    "biceps",
    "calves",
    "cardio",
    "chest",
    "forearms",
    "full_body",
    "glutes",
    "hamstrings",
    "lats",
    "lower_back",
    "neck",
    "other",
    "quadriceps",
    "shoulders",
    "traps",
    "triceps",
    "upper_back",
]

EQUIPMENT_CATEGORIES = Literal[
    "barbell",
    "bodyweight",
    "dumbbell",
    "kettlebell",
    "machine",
    "none",
    "other",
    "plate",
    "resistance_band",
    "suspension",
]

CUSTOM_EXERCISE_TYPES = Literal[
    "bodyweight_assisted_reps",
    "bodyweight_reps",
    "distance_duration",
    "duration",
    "reps_only",
    "short_distance_weight",
    "weight_duration",
    "weight_reps",
]

HEVY_REQUEST_SET_TYPE = Literal["normal", "warmup", "failure", "dropset"]


class _BaseSetMeasurements(BaseModel):
    """Shared measurement fields present on every set variant."""

    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None


class _BaseRequestSet(_BaseSetMeasurements):
    """Common fields for all request set variants (POST/PUT)."""

    type: HEVY_REQUEST_SET_TYPE = "normal"


class _BaseRequestExercise(BaseModel):
    """Common fields for all request exercise variants."""

    exercise_template_id: str
    superset_id: int | None = None
