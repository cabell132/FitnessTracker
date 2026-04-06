"""Routine POST request/response models for the Hevy API.

Endpoint: POST /v1/routines
Purpose: Create a new routine (workout template / plan).

Key differences from siblings:
- PostRoutinesRequestSet has no rpe (routines are prescriptions, not logged effort).
- PostRoutinesRequestExercise requires notes: str (Hevy rejects null on routine creation).
- PostRoutinesRequest requires notes: str and supports folder_id.

See Also:
- workout_requests.py — POST /v1/workouts (logged sessions; sets include rpe).
- routine_put_requests.py — PUT /v1/routines/{id} (sets may include custom_metric,
  rep_range).
"""

from __future__ import annotations

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.common import _BaseRequestExercise, _BaseRequestSet
from fitness_tracker.apis.hevy_app.types.routine import Routine


class PostRoutinesRequestSet(_BaseRequestSet):
    """Set row when creating a routine via POST."""


class PostRoutinesRequestExercise(_BaseRequestExercise):
    """Exercise block when creating a routine."""

    notes: str
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

    @classmethod
    def build(  # noqa: PLR0913
        cls,
        *,
        title: str,
        notes: str,
        exercises: list[PostRoutinesRequestExercise],
        folder_id: str | None = None,
    ) -> PostRoutinesRequestBody:
        """Construct the inner ``PostRoutinesRequest`` automatically.

        Args:
            title (str): Routine title.
            notes (str): Routine notes (required by the API).
            exercises (list[PostRoutinesRequestExercise]): Exercises in the routine.
            folder_id (str | None, optional): Optional folder id. Defaults to None.

        Returns:
            PostRoutinesRequestBody: Wrapper accepted by ``POST /v1/routines``.
        """
        return cls(
            routine=PostRoutinesRequest(
                title=title,
                notes=notes,
                exercises=exercises,
                folder_id=folder_id,
            ),
        )


class PostRoutinesResponse(BaseModel):
    """Response body after creating a routine."""

    routine: list[Routine]
