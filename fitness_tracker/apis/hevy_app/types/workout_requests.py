"""Workout POST request models for the Hevy API.

Endpoint: POST /v1/workouts
Purpose: Log a completed workout session.

Key differences from siblings:
- PostWorkoutsRequestSet includes rpe (logged effort / subjective intensity); routine
  variants do not.
- PostWorkoutsRequestExercise has optional notes and no rest_seconds at exercise level.

See Also:
- routine_post_requests.py — POST /v1/routines (templates; exercise notes required).
- routine_put_requests.py — PUT /v1/routines/{id} (sets may include rep_range,
  custom_metric).
"""

from __future__ import annotations

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.common import _BaseRequestExercise, _BaseRequestSet


class PostWorkoutsRequestSet(_BaseRequestSet):
    """Set row when creating a workout via POST."""

    rpe: float | None = None


class PostWorkoutsRequestExercise(_BaseRequestExercise):
    """Exercise block when creating a workout."""

    notes: str | None = None
    sets: list[PostWorkoutsRequestSet]


class PostWorkoutsRequest(BaseModel):
    """Top-level workout fields for creation."""

    title: str
    description: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    is_private: bool = False
    exercises: list[PostWorkoutsRequestExercise]
