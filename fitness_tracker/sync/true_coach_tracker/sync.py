"""Import True Coach workout payloads into the internal tracker database."""

from fitness_tracker.apis import TrueCoachClient
from fitness_tracker.apis.true_coach.types import Workout, WorkoutItem, WorkoutResponse
from fitness_tracker.database import Database
from fitness_tracker.database.models import TrueCoachExercise
from sqlalchemy.orm import Session


class TrueCoachToFitnessTrackerSyncronizer:
    """Persists True Coach workouts and items from an API snapshot."""

    def __init__(self, database: Database, source: TrueCoachClient) -> None:
        """Initiate the syncronizer with the clients.

        Args:
            database (Database): Persistence layer.
            source (TrueCoachClient): True Coach client for loading snapshots.
        """
        self._database = database
        self._source = source

    def sync_workout(self, session: Session, workout: Workout) -> None:
        """Syncronize the workout with the given id.

        Args:
            session (Session): The session to use.
            workout (Workout): The workout to syncronize.
        """
        self._database.true_coach.add_workout(session, workout)

    def sync_workout_item(self, session: Session, workout_item: WorkoutItem) -> None:
        """Syncronize the workout item with the given id.

        Args:
            session (Session): The session to use.
            workout_item (WorkoutItem): The workout item to syncronize.
        """
        self._database.true_coach.add_workout_item(session, workout_item)

        exercise = TrueCoachExercise(
            name=workout_item.name,
            id=workout_item.exercise_id,
        )
        self._database.tracker.add_exercise(session, exercise)

    def sync_workouts(self, workouts: WorkoutResponse) -> None:
        """Add a list of workouts.

        Args:
            workouts (WorkoutResponse): API response containing workouts and items.
        """
        with self._database.true_coach.get_session() as session:
            for workout in workouts.workouts:
                self.sync_workout(session=session, workout=workout)
            for workout_item in workouts.workout_items:
                self.sync_workout_item(session=session, workout_item=workout_item)
            session.commit()
