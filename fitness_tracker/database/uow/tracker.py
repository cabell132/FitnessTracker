"""Fitness tracker domain operations for UnitOfWork."""

from __future__ import annotations

from typing import Any

from fitness_tracker.database.models.tracker import (
    Exercise as TrackerExercise,
    MetricItem as TrackerMetricItem,
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

    def link_workout_item_hevy_id(self, true_coach_id: int, hevy_app_id: int) -> None:
        """Set ``hevy_app_id`` on the workout item identified by True Coach item id.

        Args:
            true_coach_id (int): ``TrueCoachWorkoutItem.id`` / ``WorkoutItem.true_coach_id``.
            hevy_app_id (int): ``HevyAppWorkoutItem.id`` to store on the tracker row.
        """
        item = self.get(TrackerWorkoutItem, true_coach_id=true_coach_id)
        if item:
            item.hevy_app_id = hevy_app_id

    def link_metric_item_to_true_coach(self, metric_item_id: int, true_coach_id: int) -> None:
        """Set ``true_coach_id`` on a metric item after a successful API sync.

        Args:
            metric_item_id (int): Primary key of the ``MetricItem`` row.
            true_coach_id (int): ``TrueCoachAssessmentItem.id`` from the API response.
        """
        item = self.get(TrackerMetricItem, id=metric_item_id)
        if item:
            item.true_coach_id = true_coach_id
