"""Routine PUT request models for the Hevy API.

Endpoint: PUT /v1/routines/{routineId}
Purpose: Update an existing routine.

Key differences from siblings:
- PutRoutinesRequestSet may include custom_metric and rep_range (prescription metadata);
  workout POST sets use rpe instead.
- PutRoutinesRequestExercise mirrors update semantics (optional routine-level notes on
  PUT; exercise notes optional).

See Also:
- workout_requests.py — POST /v1/workouts (sets use rpe).
- routine_post_requests.py — POST /v1/routines (stricter required fields on creation).
"""

from __future__ import annotations

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.common import _BaseRequestExercise, _BaseRequestSet


class PutRoutinesRepRange(BaseModel):
    """Rep range for a set in a routine update."""

    start: int | None = None
    end: int | None = None


class PutRoutinesRequestSet(_BaseRequestSet):
    """Set row when updating a routine via PUT."""

    custom_metric: float | None = None
    rep_range: PutRoutinesRepRange | None = None


class PutRoutinesRequestExercise(_BaseRequestExercise):
    """Exercise block when updating a routine."""

    rest_seconds: int | None = None
    notes: str | None = None
    sets: list[PutRoutinesRequestSet]


class PutRoutinesRequest(BaseModel):
    """Top-level routine fields for an update."""

    title: str
    notes: str | None = None
    exercises: list[PutRoutinesRequestExercise]


class PutRoutinesRequestBody(BaseModel):
    """Wrapper object expected by ``PUT /v1/routines/{routineId}``."""

    routine: PutRoutinesRequest

    @classmethod
    def build(
        cls,
        *,
        title: str,
        exercises: list[PutRoutinesRequestExercise],
        notes: str | None = None,
    ) -> PutRoutinesRequestBody:
        """Construct the inner ``PutRoutinesRequest`` automatically.

        Args:
            title (str): Routine title.
            exercises (list[PutRoutinesRequestExercise]): Exercises in the routine.
            notes (str | None, optional): Routine notes. Defaults to None.

        Returns:
            PutRoutinesRequestBody: Wrapper accepted by the routines PUT endpoint.
        """
        return cls(routine=PutRoutinesRequest(title=title, notes=notes, exercises=exercises))
