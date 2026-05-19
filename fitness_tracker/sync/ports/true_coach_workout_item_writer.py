"""Port for updating workout items and marking workouts complete on True Coach."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from fitness_tracker.apis.true_coach.types import PutWorkoutItemRequest, PutWorkoutItemResponse
from fitness_tracker.apis.true_coach.types import Workout as TrueCoachWorkoutPayload
from fitness_tracker.apis.true_coach.types import WorkoutItem as TrueCoachWorkoutItemPayload


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

    def get_recent_workout(
        self,
        workout_id: int,
    ) -> tuple[TrueCoachWorkoutPayload, list[TrueCoachWorkoutItemPayload]] | None:
        """Fetch and return the latest visible True Coach Workout snapshot.

        Args:
            workout_id (int): True Coach workout id.

        Returns:
            tuple[TrueCoachWorkoutPayload, list[TrueCoachWorkoutItemPayload]] | None:
                Latest workout and item payloads, or ``None`` when not found.
        """
        ...
