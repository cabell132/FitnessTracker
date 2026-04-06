"""Port for polling Hevy workout create/update/delete events."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from fitness_tracker.apis.hevy_app.types import PaginatedWorkoutEvents


@runtime_checkable
class HevyWorkoutEventSource(Protocol):
    """Read-side: poll Hevy for workout create/update/delete events."""

    def get_workout_events(
        self,
        since: datetime,
        page: int = 1,
        per_page: int = 10,
    ) -> PaginatedWorkoutEvents | None:
        """Fetch a page of workout events after ``since``.

        Args:
            since (datetime): Lower bound timestamp for the events query.
            page (int): 1-based page index.
            per_page (int): Number of events per page.

        Returns:
            PaginatedWorkoutEvents | None: Event page, or ``None`` when empty.
        """
        ...
