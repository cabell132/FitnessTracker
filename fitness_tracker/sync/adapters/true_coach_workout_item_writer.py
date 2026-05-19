"""Adapter wrapping :class:`TrueCoachClient` behind :class:`TrueCoachWorkoutItemWriter`."""

from __future__ import annotations

from typing import Any

from fitness_tracker.apis.true_coach.client import TrueCoachClient
from fitness_tracker.apis.true_coach.types import PutWorkoutItemRequest, PutWorkoutItemResponse
from fitness_tracker.apis.true_coach.types import Workout as TrueCoachWorkoutPayload
from fitness_tracker.apis.true_coach.types import WorkoutItem as TrueCoachWorkoutItemPayload


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

    def get_recent_workout(
        self,
        workout_id: int,
    ) -> tuple[TrueCoachWorkoutPayload, list[TrueCoachWorkoutItemPayload]] | None:
        """Fetch the latest visible True Coach workout snapshot.

        Args:
            workout_id (int): True Coach workout id.

        Returns:
            tuple[TrueCoachWorkoutPayload, list[TrueCoachWorkoutItemPayload]] | None:
                Latest workout and item payloads, or ``None`` when not found.
        """
        page = 1
        total_pages = 1
        while page <= total_pages:
            response = self._client.workouts.get(
                order="desc",
                page=page,
                per_page=100,
                states=["pending", "completed", "missed"],
            )
            if response is None:
                return None
            total_pages = response.meta.total_pages
            workout = next((row for row in response.workouts if row.id == workout_id), None)
            if workout is not None:
                items = [item for item in response.workout_items if item.workout_id == workout_id]
                return workout, items
            page += 1
        return None
