"""Port for pushing completed workouts into Hevy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fitness_tracker.apis.hevy_app.types import PostWorkoutsRequestBody, PostWorkoutsResponse


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
