"""Adapter wrapping :class:`HevyAppClient` behind :class:`HevyWorkoutWriter`."""

from __future__ import annotations

from fitness_tracker.apis.hevy_app.client import HevyAppClient
from fitness_tracker.apis.hevy_app.types import PostWorkoutsRequestBody, PostWorkoutsResponse


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
