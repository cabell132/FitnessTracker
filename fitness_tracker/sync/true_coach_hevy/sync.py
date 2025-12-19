from pathlib import Path

from fitness_tracker.apis import HevyAppClient, TrueCoachClient
from fitness_tracker.apis.hevy_app.types import (
    PostRoutinesRequest,
    PostRoutinesRequestBody,
    PostRoutinesRequestExercise,
)
from fitness_tracker.database import Database
from fitness_tracker.database.models import (
    Exercise,
    HevyAppExercise,
    TrueCoachExercise,
    TrueCoachWorkoutItem,
)
from fitness_tracker.database.repository.tracker import FitnessTrackerExerciseRepository
from fitness_tracker.llm.fitness_llm import FitnessLLM
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from tqdm import tqdm

from . import utils


class TrueCoachToHevySyncronizer:
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
            workout_id (int): The workout id to syncronize

        """
        with self._database.hevy_app.get_session() as session:
            true_coach_workout = self._database.true_coach.get_workout(session, id=workout_id)
            placeholder_exercises = self._database.hevy_app.get_placeholders()

            if true_coach_workout:
                self._database.tracker.add_workout(session, true_coach_workout)
                order = utils.get_workout_order(str(true_coach_workout.short_description))
                superset_index = utils.get_superset_index(order)
                workout_items: list[TrueCoachWorkoutItem] = sorted(
                    true_coach_workout.workout_items, key=lambda x: x.position
                )  # type: ignore
                exercises: list[PostRoutinesRequestExercise] = []
                used_exercises: list[HevyAppExercise] = []
                for item in tqdm(workout_items):  # type: ignore
                    if isinstance(item, TrueCoachWorkoutItem):
                        exercise = item.exercise
                        if isinstance(exercise, TrueCoachExercise):  # type: ignore
                            hevy_app_exercise = exercise.hevy_app  # type: ignore
                            notes = str(item.info)
                            if not isinstance(hevy_app_exercise, HevyAppExercise):  # type: ignore
                                # take the first placeholder and remove it from the list
                                hevy_app_exercise = placeholder_exercises.pop(0)
                                # add exercise to tracker
                                self._database.tracker.add_exercise(session, exercise)
                                notes = f"{item.name}\n\n{item.info}"
                        elif exercise_instance := self._database.tracker.get_exercise(
                            session, name=item.name
                        ):
                            if hevy_app_exercise := exercise_instance.hevy_app:
                                notes = str(item.info)
                            else:
                                hevy_app_exercise = placeholder_exercises.pop(0)
                                notes = f"{item.name}\n\n{item.info}"

                        else:
                            exercise_repo = FitnessTrackerExerciseRepository(session=session)
                            exercise_instance = Exercise(name=item.name)
                            exercise_repo.insert_ignore(exercise_instance)
                            hevy_app_exercise = placeholder_exercises.pop(0)
                            notes = f"{item.name}\n\n{item.info}"

                        if hevy_app_exercise in used_exercises:
                            hevy_app_exercise = placeholder_exercises.pop(0)
                            notes = f"{item.name}\n\n{item.info}"

                        if superset_index:
                            super_set = (
                                superset_index[order[item.position]["superset_group"]]
                                if order[item.position]["is_superset"]
                                else None
                            )  # type: ignore
                        else:
                            super_set = None
                        if not notes:
                            notes = str(item.name)

                        if hevy_app_exercise.name != "#####PLACEHOLDER#####":
                            sets = self._llm.parse_the_sets(
                                info=str(
                                    {"exercise_type": hevy_app_exercise.type, "info": item.info}
                                )
                            ).sets
                            if not sets:
                                sets = utils.parse_sets(str(item.info))
                        else:
                            sets = utils.parse_sets(str(item.info))

                        exercises.append(
                            PostRoutinesRequestExercise(
                                notes=notes,
                                exercise_template_id=str(hevy_app_exercise.id),
                                superset_id=super_set,
                                rest_seconds=0,
                                sets=sets,
                            )
                        )
                        used_exercises.append(hevy_app_exercise)

                routine_request = PostRoutinesRequestBody(
                    routine=PostRoutinesRequest(
                        title=f"{true_coach_workout.due.strftime('%d %b %Y')}\n{true_coach_workout.title}\n{true_coach_workout.id}",  # type: ignore
                        notes=utils.create_notes(str(true_coach_workout.short_description)),
                        exercises=exercises,
                    )
                )

                res = self._target.routines.create(routine_request)

            session.commit()
            self.insert_workout_items(session)
            session.commit()

    def insert_workout_items(self, session: Session) -> None:
        """Insert workout items.

        Args:
            session (Session): The session to use
        """
        stmnt = text(
            Path(
                "fitness_tracker/database/SQL/true_coach/tracker/workout_items/insert.sql"
            ).read_text(encoding="utf-8")
        )
        session.execute(stmnt)  # type: ignore
        session.commit()
