"""Create Hevy routines from True Coach workouts."""

from __future__ import annotations

from typing import cast

from fitness_tracker.apis.hevy_app.types import (
    PostRoutinesRequest,
    PostRoutinesRequestBody,
    PostRoutinesRequestExercise,
)
from fitness_tracker.database.models import HevyAppExercise
from fitness_tracker.sync._exercise_resolution import resolve_hevy_exercise
from fitness_tracker.sync.ports.hevy_routine_writer import HevyRoutineWriter
from fitness_tracker.sync.ports.set_parser import SetParser
from fitness_tracker.sync.ports.store_like import StoreLike
from fitness_tracker.sync.true_coach_hevy import utils
from tqdm import tqdm


class TrueCoachToHevySyncronizer:
    """Builds Hevy routine drafts from a True Coach workout and tracker links."""

    def __init__(
        self,
        store: StoreLike,
        routine_writer: HevyRoutineWriter,
        set_parser: SetParser,
    ) -> None:
        """Initiate the syncronizer with port-typed dependencies.

        Args:
            store (StoreLike): Persistence layer.
            routine_writer (HevyRoutineWriter): Port for creating Hevy routines.
            set_parser (SetParser): Port for parsing set prescriptions.
        """
        self._store = store
        self._routine_writer = routine_writer
        self._set_parser = set_parser

    def sync_workout(self, workout_id: int) -> None:  # noqa: PLR0915
        """Syncronize the workout with the given id.

        Args:
            workout_id (int): The workout id to syncronize.
        """
        with self._store.unit_of_work() as uow:
            true_coach_workout = uow.tc_get_workout(id=workout_id)
            placeholder_exercises = uow.hevy_get_placeholders()

            if true_coach_workout:
                uow.tracker_add_workout(true_coach_workout)
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
                    tc_exercise = item.exercise
                    tc_hevy_app = tc_exercise.hevy_app if hasattr(tc_exercise, "hevy_app") else None

                    hevy_app_exercise, note_override = resolve_hevy_exercise(
                        uow=uow,
                        item_name=item.name,
                        tc_exercise_hevy_app=tc_hevy_app if isinstance(tc_hevy_app, HevyAppExercise) else None,
                        placeholders=placeholder_exercises,
                        used=used_exercises,
                    )

                    if note_override:
                        notes = f"{note_override}\n\n{item.info or ''}"
                    else:
                        notes = str(item.info or "")
                    if not notes:
                        notes = str(item.name)

                    o = order.get(order_index, {})
                    is_superset = bool(o.get("is_superset"))
                    sg = o.get("superset_group")
                    if superset_index and is_superset and isinstance(sg, str):
                        super_set = superset_index.get(sg)
                    else:
                        super_set = None

                    if hevy_app_exercise.name != "#####PLACEHOLDER#####":
                        sets = self._set_parser.parse_the_sets(
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

                self._routine_writer.create_routine(routine_request)

            uow.insert_tc_tracker_workout_items()
