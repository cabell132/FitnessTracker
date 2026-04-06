"""Workout request body and response wrappers for the Hevy API."""

from __future__ import annotations

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.workout import Workout
from fitness_tracker.apis.hevy_app.types.workout_requests import PostWorkoutsRequest


class PostWorkoutsRequestBody(BaseModel):
    """Wrapper object expected by the workouts POST endpoint."""

    workout: PostWorkoutsRequest


class PostWorkoutsResponse(BaseModel):
    """Response body after creating a workout."""

    workout: list[Workout]
