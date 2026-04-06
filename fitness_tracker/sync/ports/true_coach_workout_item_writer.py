"""Port for updating workout items and marking workouts complete on True Coach."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fitness_tracker.apis.true_coach.types import PutWorkoutItemRequest, PutWorkoutItemResponse


@runtime_checkable
class TrueCoachWorkoutItemWriter(Protocol):
    """Update workout items and mark workouts complete on True Coach."""

    def update_workout_item(
        self, item_id: int, item: PutWorkoutItemRequest
    ) -> PutWorkoutItemResponse | None:
        """Apply a workout item update via PUT.

        Args:
            item_id (int): True Coach workout item id.
            item (PutWorkoutItemRequest): Fields to persist.

        Returns:
            PutWorkoutItemResponse | None: Updated item payload, or ``None`` if empty.
        """
        ...

    def mark_workout_completed(self, workout_id: int) -> Any:
        """Send the mark-as-completed state transition for a workout.

        Args:
            workout_id (int): True Coach workout id.

        Returns:
            Any: API response body.
        """
        ...
