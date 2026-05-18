"""Port for pushing completed workouts into Hevy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fitness_tracker.apis.hevy_app.types import (
    PostWorkoutsRequestBody,
    PostWorkoutsResponse,
    Workout,
)


@runtime_checkable
class HevyWorkoutWriter(Protocol):
    """Write-side: push a completed workout into Hevy."""

    def create_workout(self, workout: PostWorkoutsRequestBody) -> PostWorkoutsResponse | None:
        """Create a workout from the given request body.

        Args:
            workout (PostWorkoutsRequestBody): Typed workout payload accepted by the Hevy API.

        Returns:
            PostWorkoutsResponse | None: Parsed response, or ``None`` when the API returns empty.
        """
        ...

    def find_workout_by_true_coach_id(self, workout_id: int) -> Workout | None:
        """Find an existing remote backfilled Workout by source True Coach id marker.

        Args:
            workout_id (int): Source True Coach Workout id.

        Returns:
            Workout | None: Matching remote Workout when found.
        """
        ...

    def get_workout(self, workout_id: str) -> Workout | None:
        """Fetch one remote Hevy Workout by id.

        Args:
            workout_id (str): Hevy Workout id.

        Returns:
            Workout | None: Matching remote Workout when found.
        """
        ...
