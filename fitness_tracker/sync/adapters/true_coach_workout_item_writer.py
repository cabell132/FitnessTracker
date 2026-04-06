"""Adapter wrapping :class:`TrueCoachClient` behind :class:`TrueCoachWorkoutItemWriter`."""

from __future__ import annotations

from typing import Any

from fitness_tracker.apis.true_coach.client import TrueCoachClient
from fitness_tracker.apis.true_coach.types import PutWorkoutItemRequest, PutWorkoutItemResponse


class TrueCoachWorkoutItemWriterAdapter:
    """Delegates workout item updates and completion to the True Coach REST client."""

    def __init__(self, client: TrueCoachClient) -> None:
        """Wrap a True Coach client for workout item writes.

        Args:
            client (TrueCoachClient): True Coach API client.
        """
        self._client = client

    def update_workout_item(
        self, item_id: int, item: PutWorkoutItemRequest
    ) -> PutWorkoutItemResponse | None:
        """Apply a workout item update via PUT.

        Args:
            item_id (int): True Coach workout item id.
            item (PutWorkoutItemRequest): Fields to persist.

        Returns:
            PutWorkoutItemResponse | None: Updated item or ``None``.
        """
        return self._client.workouts.update_workout_item(item_id, item)

    def mark_workout_completed(self, workout_id: int) -> Any:
        """Send the mark-as-completed state transition.

        Args:
            workout_id (int): True Coach workout id.

        Returns:
            Any: API response body.
        """
        return self._client.workouts.mark_as_completed(workout_id)
