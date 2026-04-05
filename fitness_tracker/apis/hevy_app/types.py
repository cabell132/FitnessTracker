"""Pydantic models for Hevy App API payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
    equipment: Literal[
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
    is_custom: bool


class ExerciseResponse(BaseModel):
    """Paginated list of exercise templates."""

    page: int
    page_count: int
    exercise_templates: list[ExerciseTemplate]


class Set(BaseModel):
    """One logged set inside a workout or routine block."""

    index: int
    type: str
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    rpe: int | None = None


class Exercise(BaseModel):
    """Exercise block with nested sets inside a workout or routine."""

    index: int
    title: str
    notes: str
    exercise_template_id: str
    superset_id: int | None = None
    sets: list[Set]


class Workout(BaseModel):
    """Full workout payload including exercise blocks."""

    id: str
    title: str
    description: str
    start_time: str
    end_time: str
    updated_at: str
    created_at: str
    exercises: list[Exercise]


class Routine(BaseModel):
    """Saved routine (template) returned by the routines API."""

    id: str
    title: str
    updated_at: str
    created_at: str
    exercises: list[Exercise]


class WorkoutResponse(BaseModel):
    """Paginated workouts list."""

    page: int
    page_count: int
    workouts: list[Workout]


class UpdatedWorkout(BaseModel):
    """Workout change event from the events feed."""

    type: str
    workout: Workout


class DeletedWorkout(BaseModel):
    """Deletion event from the workout events feed."""

    type: str
    id: str
    deleted_at: str


class PaginatedWorkoutEvents(BaseModel):
    """Paged workout events used for incremental sync."""

    page: int
    page_count: int
    events: list[UpdatedWorkout | DeletedWorkout] = Field(default_factory=list)


class PostRoutinesRequestSet(BaseModel):
    """Set row when creating a routine via POST."""

    type: Literal["normal", "warmup", "failure", "dropset"] = Field(
        default="normal", description="The type of the set", example="normal"
    )
    weight_kg: float | None = Field(
        default=None, description="The weight of the set in kg", example=10.0
    )
    reps: int | None = Field(
        default=None, description="The number of reps in the set", example=10
    )
    distance_meters: int | None = Field(
        default=None, description="The distance in meters", example=100
    )
    duration_seconds: int | None = Field(
        default=None, description="The duration in seconds", example=60
    )


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


class PostWorkoutsRequestSet(BaseModel):
    """Set row when creating a workout via POST."""

    type: Literal["normal", "warmup", "failure", "dropset"] = Field(
        default="normal", description="The type of the set", example="normal"
    )
    weight_kg: float | None = Field(
        default=None, description="The weight of the set in kg", example=10.0
    )
    reps: int | None = Field(
        default=None, description="The number of reps in the set", example=10
    )
    distance_meters: int | None = Field(
        default=None, description="The distance in meters", example=100
    )
    duration_seconds: int | None = Field(
        default=None, description="The duration in seconds", example=60
    )
    rpe: float | None = Field(
        default=None,
        description="e Rating of Perceived Exertion (RPE)",
        example=5,
    )


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
    start_time: str | None = Field(
        default=None,
        description="The time the workout started.",
        example="2024-08-14T12:00:00Z",
    )
    end_time: str | None = Field(
        default=None,
        description="The time the workout ended.",
        example="2024-08-14T13:00:00Z",
    )
    is_private: bool = Field(
        default=False,
        description="A boolean indicating if the workout is private.",
        example=False,
    )
    exercises: list[PostWorkoutsRequestExercise]


class PostWorkoutsRequestBody(BaseModel):
    """Wrapper object expected by the workouts POST endpoint."""

    workout: PostWorkoutsRequest


class PostWorkoutsResponse(BaseModel):
    """Response body after creating a workout."""

    workout: list[Workout]
