"""Port for pushing routine drafts into Hevy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fitness_tracker.apis.hevy_app.types import PostRoutinesRequestBody, PostRoutinesResponse


@runtime_checkable
class HevyRoutineWriter(Protocol):
    """Write-side: push a routine draft into Hevy."""

    def create_routine(self, routine: PostRoutinesRequestBody) -> PostRoutinesResponse | None:
        """Create a routine draft from the given request body.

        Args:
            routine (PostRoutinesRequestBody): Typed routine payload accepted by the Hevy API.

        Returns:
            PostRoutinesResponse | None: Parsed response, or ``None`` when the API returns empty.
        """
        ...
