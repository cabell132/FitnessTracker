"""Adapter wrapping :class:`HevyAppClient` behind :class:`HevyRoutineWriter`."""

from __future__ import annotations

from fitness_tracker.apis.hevy_app.client import HevyAppClient
from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestBody, PostRoutinesResponse


class HevyRoutineWriterAdapter:
    """Delegates routine creation to the Hevy REST client."""

    def __init__(self, client: HevyAppClient) -> None:
        """Wrap a Hevy client for routine writes.

        Args:
            client (HevyAppClient): Hevy API client.
        """
        self._client = client

    def create_routine(self, routine: PostRoutinesRequestBody) -> PostRoutinesResponse | None:
        """Create a routine draft via the Hevy API.

        Args:
            routine (PostRoutinesRequestBody): Typed routine payload.

        Returns:
            PostRoutinesResponse | None: Parsed response or ``None``.
        """
        return self._client.routines.create(routine)
