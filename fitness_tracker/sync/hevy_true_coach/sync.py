from fitness_tracker.apis import TrueCoachClient
from fitness_tracker.apis.true_coach.types import PutWorkoutItemRequest
from fitness_tracker.database import Database
from fitness_tracker.database.models import (
    HevyAppExercise,
    HevyAppWorkout,
    HevyAppWorkoutItem,
    TrueCoachWorkoutItem,
)
from fitness_tracker.sync.hevy_true_coach.utils import mapping


class HevyToTrueCoachSyncronizer:
    """Syncronizer class."""

    def __init__(self, database: Database, target: TrueCoachClient) -> None:
        """Initiate the syncronizer with the clients."""
        self._database = database
        self._target = target

    def sync_workout(self, hevy_workout_id: str) -> None:
        """Syncronize the workout with the given id.

        Args:
            hevy_workout_id (int): The workout id to syncronize

        """
        with self._database.hevy_app.get_session() as session:
            hevy_app_workout = self._database.hevy_app.get_workout(session, id=hevy_workout_id)
            if not isinstance(hevy_app_workout, HevyAppWorkout):
                msg = f"Workout with id {hevy_workout_id} not found"
                raise TypeError(msg)

            true_coach_workout = hevy_app_workout.true_coach
            if not true_coach_workout:
                msg = f"True coach workout not found for workout with id {hevy_workout_id}"
                raise TypeError(msg)

            hevy_app_workout_items: list[HevyAppWorkoutItem] = hevy_app_workout.workout_items  # type: ignore

            for item in hevy_app_workout_items:
                exercise = item.exercise
                if isinstance(exercise, HevyAppExercise):  # type: ignore
                    if exercise.type not in mapping:
                        msg = f"Exercise type {exercise.type} is not supported yet"
                        raise ValueError(msg)
                    result = mapping[exercise.type](item.sets)

                    true_coach_workout_item = item.true_coach
                    if isinstance(true_coach_workout_item, TrueCoachWorkoutItem):
                        update_workout_item = PutWorkoutItemRequest(
                            id=true_coach_workout_item.id,
                            workout_id=true_coach_workout_item.workout_id,
                            name=true_coach_workout_item.name,
                            info=true_coach_workout_item.info,
                            result=result.strip(),
                            is_circuit=true_coach_workout_item.is_circuit,
                            state="completed",
                            state_event="mark_as_completed",
                            position=true_coach_workout_item.position,
                            exercise_id=true_coach_workout_item.exercise_id,
                            assessment_id=true_coach_workout_item.assessment_id,
                        )

                        res = self._target.workouts.update_workout_item(
                            update_workout_item.id, update_workout_item
                        )

                        self._database.true_coach.update_workout_item(session, res.workout_item)
                    else:
                        msg = (
                            f"True coach workout item not found for workout item with id {item.id}"
                        )
                        print(msg)

            res = self._target.workouts.mark_as_completed(true_coach_workout.id)

            session.commit()
