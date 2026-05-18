"""Import True Coach workout payloads into the internal tracker database."""

from fitness_tracker.apis import TrueCoachClient
from fitness_tracker.apis.true_coach.types import Workout, WorkoutItem, WorkoutResponse
from fitness_tracker.database import Store
from fitness_tracker.database.models import TrueCoachExercise
from fitness_tracker.database.tx import Tx


class TrueCoachToFitnessTrackerSyncronizer:
    """Persists True Coach workouts and items from an API snapshot."""

    def __init__(self, store: Store, source: TrueCoachClient) -> None:
        """Initiate the syncronizer with the clients.

        Args:
            store (Store): Persistence layer.
            source (TrueCoachClient): True Coach client for loading snapshots.
        """
        self._store = store
        self._source = source

    def sync_workout(self, uow: Tx, workout: Workout) -> None:
        """Syncronize the workout with the given id.

        Args:
            uow (Tx): Active unit of work.
            workout (Workout): The workout to syncronize.
        """
        uow.true_coach.add_workout(workout)

    def sync_workout_item(self, uow: Tx, workout_item: WorkoutItem) -> None:
        """Syncronize the workout item with the given id.

        Args:
            uow (Tx): Active unit of work.
            workout_item (WorkoutItem): The workout item to syncronize.
        """
        if workout_item.exercise_id is not None:
            exercise = TrueCoachExercise(
                name=workout_item.name,
                id=workout_item.exercise_id,
            )
            uow.session.merge(exercise)
            uow.tracker.add_exercise(exercise)

        uow.true_coach.add_workout_item(workout_item)

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
