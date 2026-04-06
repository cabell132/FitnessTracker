"""Import True Coach workout payloads into the internal tracker database."""

from __future__ import annotations

from fitness_tracker.apis.true_coach.types import Workout, WorkoutItem, WorkoutResponse
from fitness_tracker.database.models import TrueCoachExercise
from fitness_tracker.database.uow import UnitOfWork
from fitness_tracker.sync.ports.store_like import StoreLike


class TrueCoachToFitnessTrackerSyncronizer:
    """Persists True Coach workouts and items from an API snapshot."""

    def __init__(self, store: StoreLike) -> None:
        """Initiate the syncronizer with port-typed dependencies.

        Args:
            store (StoreLike): Persistence layer.
        """
        self._store = store

    def sync_workout(self, uow: UnitOfWork, workout: Workout) -> None:
        """Syncronize the workout with the given id.

        Args:
            uow (UnitOfWork): Active unit of work.
            workout (Workout): The workout to syncronize.
        """
        uow.tc_add_workout(workout)

    def sync_workout_item(self, uow: UnitOfWork, workout_item: WorkoutItem) -> None:
        """Syncronize the workout item with the given id.

        Args:
            uow (UnitOfWork): Active unit of work.
            workout_item (WorkoutItem): The workout item to syncronize.
        """
        uow.tc_add_workout_item(workout_item)

        exercise = TrueCoachExercise(
            name=workout_item.name,
            id=workout_item.exercise_id,
        )
        uow.tracker_add_exercise(exercise)

    def sync_workouts(self, workouts: WorkoutResponse) -> None:
        """Add a list of workouts.

        Args:
            workouts (WorkoutResponse): API response containing workouts and items.
        """
        with self._store.unit_of_work() as uow:
            for workout in workouts.workouts:
                self.sync_workout(uow=uow, workout=workout)
            for workout_item in workouts.workout_items:
                self.sync_workout_item(uow=uow, workout_item=workout_item)
