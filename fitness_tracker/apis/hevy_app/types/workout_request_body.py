"""Workout request body and response wrappers for the Hevy API."""

from __future__ import annotations

from pydantic import BaseModel

from fitness_tracker.apis.hevy_app.types.workout import Workout
from fitness_tracker.apis.hevy_app.types.workout_requests import (
    PostWorkoutsRequest,
    PostWorkoutsRequestExercise,
)


class PostWorkoutsRequestBody(BaseModel):
    """Wrapper object expected by the workouts POST endpoint."""

    workout: PostWorkoutsRequest

    @classmethod
    def build(  # noqa: PLR0913
        cls,
        *,
        title: str,
        exercises: list[PostWorkoutsRequestExercise],
        description: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        is_private: bool = False,
    ) -> PostWorkoutsRequestBody:
        """Construct the inner ``PostWorkoutsRequest`` automatically.

        Args:
            title (str): Workout title.
            exercises (list[PostWorkoutsRequestExercise]): Logged exercises.
            description (str | None, optional): Workout description. Defaults to None.
            start_time (str | None, optional): ISO start time. Defaults to None.
            end_time (str | None, optional): ISO end time. Defaults to None.
            is_private (bool, optional): Whether the workout is private. Defaults to
                False.

        Returns:
            PostWorkoutsRequestBody: Wrapper accepted by ``POST /v1/workouts``.
        """
        return cls(
            workout=PostWorkoutsRequest(
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                is_private=is_private,
                exercises=exercises,
            ),
        )


class PostWorkoutsResponse(BaseModel):
    """Response body after creating a workout."""

    workout: list[Workout]
