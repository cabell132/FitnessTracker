"""Fitness tracker domain operations for UnitOfWork."""

from __future__ import annotations

from typing import Any

from fitness_tracker.database.models.tracker import (
    Exercise as TrackerExercise,
    Workout as TrackerWorkout,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import (
    TrueCoachExercise,
    TrueCoachWorkout,
)
from fitness_tracker.database.uow.base import CrudMixin


class TrackerMixin(CrudMixin):
    """Canonical fitness tracker persistence helpers mixed into UnitOfWork."""

    def tracker_add_workout(self, workout: TrueCoachWorkout) -> None:
        """Insert a canonical workout row linked from a True Coach workout.

        Args:
            workout (TrueCoachWorkout): Source row to mirror.
        """
        instance = TrackerWorkout(
            title=workout.title,
            description=workout.short_description,
            true_coach_id=workout.id,
        )
        self.insert_ignore(instance)

    def tracker_get_workout(self, **kwargs: Any) -> TrackerWorkout | None:
        """Fetch a tracker workout by filter kwargs.

        Args:
            **kwargs (Any): Column filters.

        Returns:
            TrackerWorkout | None: Matching row if any.
        """
        return self.get(TrackerWorkout, **kwargs)

    def tracker_add_exercise(self, exercise: TrueCoachExercise) -> None:
        """Ensure a canonical exercise exists and link it to True Coach ids.

        Args:
            exercise (TrueCoachExercise): Source exercise row.
        """
        if self.get(TrackerExercise, true_coach_id=exercise.id):
            return

        existing = self.get(TrackerExercise, name=exercise.name)
        if existing:
            existing.true_coach_id = exercise.id
            return

        entry = TrackerExercise(
            name=exercise.name,
            true_coach_id=exercise.id,
        )
        self.add(entry)

    def tracker_get_exercise(self, **kwargs: Any) -> TrackerExercise | None:
        """Fetch a tracker exercise by filter kwargs.

        Args:
            **kwargs (Any): Column filters.

        Returns:
            TrackerExercise | None: Matching row if any.
        """
        return self.get(TrackerExercise, **kwargs)

    def tracker_get_workout_item_by_index(
        self,
        workout_id: int,
        index: int,
    ) -> TrackerWorkoutItem | None:
        """Return the workout item at a given position within a workout.

        Args:
            workout_id (int): Parent workout primary key.
            index (int): Item position (``WorkoutItem.position``).

        Returns:
            TrackerWorkoutItem | None: Matching row if any.
        """
        return self.get(TrackerWorkoutItem, workout_id=workout_id, position=index)
