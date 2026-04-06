"""Adapter wrapping :class:`HevyAppClient` behind :class:`HevyWorkoutEventSource`."""

from __future__ import annotations

from datetime import datetime

from fitness_tracker.apis.hevy_app.client import HevyAppClient
from fitness_tracker.apis.hevy_app.types import PaginatedWorkoutEvents


class HevyWorkoutEventSourceAdapter:
    """Delegates workout event polling to the Hevy REST client."""

    def __init__(self, client: HevyAppClient) -> None:
        """Wrap a Hevy client for event polling.

        Args:
            client (HevyAppClient): Hevy API client.
        """
        self._client = client

    def get_workout_events(
        self,
        since: datetime,
        page: int = 1,
        per_page: int = 10,
    ) -> PaginatedWorkoutEvents | None:
        """Fetch a page of workout events after ``since``.

        Args:
            since (datetime): Lower bound timestamp.
            page (int): 1-based page index.
            per_page (int): Events per page.

        Returns:
            PaginatedWorkoutEvents | None: Event page or ``None``.
        """
        return self._client.workouts.get_workout_events(since=since, page=page, per_page=per_page)
