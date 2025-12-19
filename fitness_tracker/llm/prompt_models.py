from typing import Literal, Optional

from pydantic import BaseModel, Field

from fitness_tracker.apis.hevy_app.types import MUSCLE_GROUPS, PostRoutinesRequestSet


class PostRoutinesRequestSets(BaseModel):
    sets: list[PostRoutinesRequestSet] = Field(description="The sets of the routine")


class Exercise(BaseModel):
    title: str = Field(description="The title of the exercise")
    exercise_type: Literal[
        "bodyweight_assisted_reps",
        "bodyweight_reps",
        "distance_duration",
        "duration",
        "reps_only",
        "short_distance_weight",
        "weight_duration",
        "weight_reps",
    ] = Field(description="The type of the exercise")
    muscle_group: MUSCLE_GROUPS = Field(description="The primary muscle group of the exercise")
    other_muscles: list[MUSCLE_GROUPS] = Field(
        description="The secondary muscle groups of the exercise"
    )
    equipment_category: Literal[
        "barbell",
        "dumbbell",
        "kettlebell",
        "machine",
        "none",
        "other",
        "plate",
        "resistance_band",
        "suspension",
    ] = Field(description="The equipment of the exercise")


class WorkoutItemLink(BaseModel):
    hevy_app_id: Optional[int] = Field(
        description="The id of the Hevy App workout item", default=None
    )
    true_coach_id: Optional[int] = Field(
        description="The id of the TrueCoach workout item", default=None
    )


class WorkoutItemLinkList(BaseModel):
    links: list[WorkoutItemLink] = Field(
        description="The links between the Hevy App and TrueCoach workout items"
    )


class Sets(BaseModel):
    sets: list["Set"] = Field(description="The sets of the routine")


class Set(BaseModel):
    type: Literal["normal", "warmup", "failure", "dropset"] = Field(
        default="normal", description="The type of the set", example="normal"
    )
    weight_kg: Optional[float] = Field(
        default=None, description="The weight of the set in kg", example=10.0
    )
    reps: Optional[int] = Field(
        default=None, description="The number of reps in the set", example=10
    )
    distance_meters: Optional[int] = Field(
        default=None, description="The distance in meters", example=100
    )
    duration_seconds: Optional[int] = Field(
        default=None, description="The duration in seconds", example=60
    )
