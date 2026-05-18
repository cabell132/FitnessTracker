"""Create Hevy routines from True Coach workouts."""

from __future__ import annotations

from typing import cast

from fitness_tracker.apis import HevyAppClient, TrueCoachClient
from fitness_tracker.apis.hevy_app.types import (
    PostRoutinesRequest,
    PostRoutinesRequestBody,
    PostRoutinesRequestExercise,
)
from fitness_tracker.database import Store
from fitness_tracker.database.models import (
    HevyAppExercise,
    TrueCoachExercise,
)
from fitness_tracker.database.models.tracker import Exercise as TrackerExercise
from fitness_tracker.llm.fitness_llm import FitnessLLM
from fitness_tracker.sync.true_coach_hevy import utils
from tqdm import tqdm


class TrueCoachToHevySyncronizer:
    """Builds Hevy routine drafts from a True Coach workout and tracker links."""

    def __init__(  # noqa: PLR0913
        self,
        store: Store,
        source: TrueCoachClient,
        target: HevyAppClient,
        llm: FitnessLLM,
    ) -> None:
        """Initiate the syncronizer with the clients.

        Args:
            store (Store): Persistence layer.
            source (TrueCoachClient): True Coach API client.
            target (HevyAppClient): Hevy API client for routine creation.
            llm (FitnessLLM): Parser for set prescriptions.
        """
        self._store = store
        self._target = target
        self._source = source
        self._llm = llm

    def sync_workout(self, workout_id: int) -> None:  # noqa: C901, PLR0912, PLR0915
        """Syncronize the workout with the given id.

        Args:
            workout_id (int): The workout id to syncronize.
        """
        with self._store.unit_of_work() as uow:
            true_coach_workout = uow.true_coach.get_workout(id=workout_id)
            placeholder_exercises = uow.hevy.get_placeholders()

            if true_coach_workout:
                uow.tracker.add_workout(true_coach_workout)
                desc = str(true_coach_workout.short_description or "")
                order = utils.get_workout_order(desc)
                superset_index = utils.get_superset_index(order)
                raw_items = list(true_coach_workout.workout_items)
                workout_items = sorted(
                    raw_items,
                    key=lambda x: cast(int, x.position) if x.position is not None else 0,
                )
                exercises: list[PostRoutinesRequestExercise] = []
                used_exercises: list[HevyAppExercise] = []
                for order_index, item in enumerate(tqdm(workout_items), start=1):
                    exercise = item.exercise
                    if isinstance(exercise, TrueCoachExercise):
                        hevy_app_exercise = exercise.hevy_app
                        notes = str(item.info or "")
                        if not isinstance(hevy_app_exercise, HevyAppExercise):
                            hevy_app_exercise = placeholder_exercises.pop(0)
                            uow.tracker.add_exercise(exercise)
                            notes = f"{item.name}\n\n{item.info or ''}"
                    elif exercise_instance := uow.tracker.get_exercise(name=item.name):
                        if hevy_app_exercise := exercise_instance.hevy_app:
                            notes = str(item.info or "")
                        else:
                            hevy_app_exercise = placeholder_exercises.pop(0)
                            notes = f"{item.name}\n\n{item.info or ''}"

                    else:
                        exercise_instance = TrackerExercise(name=item.name)
                        uow.session.insert_ignore(exercise_instance)
                        hevy_app_exercise = placeholder_exercises.pop(0)
                        notes = f"{item.name}\n\n{item.info or ''}"

                    if hevy_app_exercise in used_exercises:
                        hevy_app_exercise = placeholder_exercises.pop(0)
                        notes = f"{item.name}\n\n{item.info or ''}"

                    o = order.get(order_index, {})
                    is_superset = bool(o.get("is_superset"))
                    sg = o.get("superset_group")
                    if superset_index and is_superset and isinstance(sg, str):
                        super_set = superset_index.get(sg)
                    else:
                        super_set = None
                    if not notes:
                        notes = str(item.name)

                    if hevy_app_exercise.name != "#####PLACEHOLDER#####":
                        sets = self._llm.parse_the_sets(
                            info=str({"exercise_type": hevy_app_exercise.type, "info": item.info})
                        ).sets
                        if not sets:
                            sets = utils.parse_sets(str(item.info or ""))
                    else:
                        sets = utils.parse_sets(str(item.info or ""))

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

                due = true_coach_workout.due
                due_s = due.strftime("%d %b %Y") if due is not None else ""
                wo_title = true_coach_workout.title or ""
                routine_request = PostRoutinesRequestBody(
                    routine=PostRoutinesRequest(
                        title=f"{due_s}\n{wo_title}\n{true_coach_workout.id}",
                        notes=utils.create_notes(desc),
                        exercises=exercises,
                    )
                )

                self._target.routines.create(routine_request)

            uow.cross_domain.insert_tc_tracker_workout_items()
