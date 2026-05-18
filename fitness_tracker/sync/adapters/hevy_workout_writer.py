"""Adapter wrapping :class:`HevyAppClient` behind :class:`HevyWorkoutWriter`."""

from __future__ import annotations

from fitness_tracker.apis.hevy_app.client import HevyAppClient
from fitness_tracker.apis.hevy_app.types import (
    PostWorkoutsRequestBody,
    PostWorkoutsResponse,
    Workout,
)


class HevyWorkoutWriterAdapter:
    """Delegates workout creation to the Hevy REST client."""

    def __init__(self, client: HevyAppClient) -> None:
        """Wrap a Hevy client for workout writes.

        Args:
            client (HevyAppClient): Hevy API client.
        """
        self._client = client

    def create_workout(self, workout: PostWorkoutsRequestBody) -> PostWorkoutsResponse | None:
        """Create a workout via the Hevy API.

        Args:
            workout (PostWorkoutsRequestBody): Typed workout payload.

        Returns:
            PostWorkoutsResponse | None: Parsed response or ``None``.
        """
        return self._client.workouts.create(workout)

    def get_workout(self, workout_id: str) -> Workout | None:
        """Fetch a workout by id via the Hevy API.

        Args:
            workout_id (str): Hevy Workout id.

        Returns:
            Workout | None: Parsed workout, or ``None``.
        """
        return self._client.workouts.get_workout(workout_id)

    def find_workout_by_true_coach_id(self, workout_id: int) -> Workout | None:
        """Find a remote Workout carrying the source True Coach idempotency marker.

        Args:
            workout_id (int): Source True Coach Workout id.

        Returns:
            Workout | None: First matching remote Workout, if present.
        """
        marker = f"True Coach Workout {workout_id}"
        page = 1
        while response := self._client.workouts.get(page=page, per_page=10):
            for workout in response.workouts:
                if marker in (workout.description or "") or marker in workout.title:
                    return workout
            if page >= response.page_count:
                return None
            page += 1
        return None
