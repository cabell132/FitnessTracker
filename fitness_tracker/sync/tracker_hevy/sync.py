from fitness_tracker.apis import HevyAppClient, TrueCoachClient
from fitness_tracker.apis.hevy_app.types import (
    PostWorkoutsRequest,
    PostWorkoutsRequestBody,
    PostWorkoutsRequestExercise,
    PostWorkoutsRequestSet,
)
from fitness_tracker.database import Database
from fitness_tracker.database.models import Exercise, HevyAppExercise, Sets, WorkoutItem
from fitness_tracker.llm.fitness_llm import FitnessLLM
from tqdm import tqdm
from datetime import datetime, timedelta

from . import utils


class TrackerToHevySyncronizer:
    """Syncronizer class"""

    def __init__(
        self, database: Database, source: TrueCoachClient, target: HevyAppClient, llm: FitnessLLM
    ) -> None:
        """Initiate the syncronizer with the clients"""
        self._database = database
        self._target = target
        self._source = source
        self._llm = llm

    def sync_workout(self, workout_id: int) -> None:
        """Syncronize the workout with the given id.

        Args:
            workout_id (int): The true coach workout id to syncronize

        """
        with self._database.hevy_app.get_session() as session:
            workout = self._database.tracker.get_workout(session, true_coach_id=workout_id)
            placeholder_exercises = self._database.hevy_app.get_placeholders()

            if workout:
                order = utils.get_workout_order(str(workout.true_coach.short_description))
                superset_index = utils.get_superset_index(order)
                workout_items: list[WorkoutItem] = sorted(
                    workout.workout_items, key=lambda x: x.position
                )  # type: ignore
                exercises: list[PostWorkoutsRequestExercise] = []
                used_exercises: list[HevyAppExercise] = []
                for item in tqdm(workout_items):  # type: ignore
                    note = None
                    exercise = item.exercise
                    if item.true_coach.state == "completed":
                        if isinstance(exercise, Exercise):  # type: ignore
                            hevy_app_exercise = exercise.hevy_app  # type: ignore
                            if not isinstance(hevy_app_exercise, HevyAppExercise):  # type: ignore
                                # take the first placeholder and remove it from the list
                                hevy_app_exercise = placeholder_exercises.pop(0)
                                # add exercise to tracker
                                if hevy_app_exercise.name != "#####PLACEHOLDER#####":
                                    self._database.tracker.add_exercise(session, exercise)
                            # elif hevy_app_exercise in used_exercises:
                            #     hevy_app_exercise = placeholder_exercises.pop(0)
                        else:
                            hevy_app_exercise = placeholder_exercises.pop(0)

                        if superset_index:
                            super_set = (
                                superset_index[order[item.position]["superset_group"]]
                                if order[item.position]["is_superset"]
                                else None
                            )  # type: ignore
                        else:
                            super_set = None

                        if hevy_app_exercise.name != "#####PLACEHOLDER#####":
                            sets = self.get_sets(item.sets)
                        else:
                            note = item.true_coach.name
                            sets = [PostWorkoutsRequestSet(**item.model_dump()) for item in self._llm.parse_the_sets(
                                info=str({"exercise_type": hevy_app_exercise.type, "info": item.true_coach.info})
                            ).sets]
                            if not sets:
                                sets = [PostWorkoutsRequestSet(**item.model_dump()) for item in utils.parse_sets(str(item.true_coach.info))]


                        exercises.append(
                            PostWorkoutsRequestExercise(
                                notes=note,
                                exercise_template_id=str(hevy_app_exercise.id),
                                superset_id=super_set,
                                sets=sets,
                            )
                        )
                        used_exercises.append(hevy_app_exercise)

                workout_request = PostWorkoutsRequestBody(
                    workout=PostWorkoutsRequest(
                        title=f"{workout.true_coach.due.strftime('%d %b %Y')}\n{workout.title}\n{workout.true_coach_id}",  # type: ignore
                        start_time=(workout.start_date).isoformat(),  # type: ignore
                        end_time=(workout.end_date).isoformat(),  # type: ignore
                        exercises=exercises,
                    )
                )

                res = self._target.workouts.create(workout_request)

            session.commit()
            return res

    def get_sets(self, sets: list[Sets]) -> list[PostWorkoutsRequestSet]:
        """Get the sets from the info string

        Args:
            sets (list[Sets]): The sets

        Returns:
            list[PostWorkoutsRequestSet]: The transformed sets

        """
        new_sets: list[PostWorkoutsRequestSet] = []
        new_sets.extend(
            PostWorkoutsRequestSet(
                type=item.type,
                weight_kg=item.weight_kg,
                reps=item.reps,
                distance_meters=item.distance_meters,
                duration_seconds=item.duration_seconds,
            )
            for item in sets
        )
        return new_sets
