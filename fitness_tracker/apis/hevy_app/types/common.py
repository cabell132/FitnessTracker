"""Shared type aliases for Hevy API payloads."""

from __future__ import annotations

from typing import Literal

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
