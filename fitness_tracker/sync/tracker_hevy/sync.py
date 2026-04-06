"""Create Hevy workouts from internal tracker rows linked to True Coach."""

from __future__ import annotations

from typing import Literal, cast

from fitness_tracker.apis.hevy_app.types import (
    PostWorkoutsRequest,
    PostWorkoutsRequestBody,
    PostWorkoutsRequestExercise,
    PostWorkoutsRequestSet,
)
from fitness_tracker.database.models import Exercise, HevyAppExercise, Sets
from fitness_tracker.sync.ports.hevy_workout_writer import HevyWorkoutWriter
from fitness_tracker.sync.ports.set_parser import SetParser
from fitness_tracker.sync.ports.store_like import StoreLike
from fitness_tracker.sync.tracker_hevy import utils
from tqdm import tqdm

SetType = Literal["normal", "warmup", "failure", "dropset"]


def _coerce_set_type(raw: str) -> SetType:
    if raw in ("normal", "warmup", "failure", "dropset"):
        return cast(SetType, raw)
    return "normal"


class TrackerToHevySyncronizer:
    """Posts a Hevy workout built from tracker state and True Coach metadata."""

    def __init__(
        self,
        store: StoreLike,
        workout_writer: HevyWorkoutWriter,
        set_parser: SetParser,
    ) -> None:
        """Initiate the syncronizer with port-typed dependencies.

        Args:
            store (StoreLike): Persistence layer.
            workout_writer (HevyWorkoutWriter): Port for creating Hevy workouts.
            set_parser (SetParser): Port for parsing set prescriptions.
        """
        self._store = store
        self._workout_writer = workout_writer
        self._set_parser = set_parser

    def sync_workout(self, workout_id: int) -> None:  # noqa: PLR0912, PLR0915
        """Syncronize the workout with the given id.

        Args:
            workout_id (int): The true coach workout id to syncronize.
        """
        with self._store.unit_of_work() as uow:
            workout = uow.tracker_get_workout(true_coach_id=workout_id)
            placeholder_exercises = uow.hevy_get_placeholders()

            if workout is not None and workout.true_coach is not None:
                tc_workout = workout.true_coach
                desc = str(tc_workout.short_description or "")
                order = utils.get_workout_order(desc)
                superset_index = utils.get_superset_index(order)
                workout_items = sorted(
                    workout.workout_items,
                    key=lambda x: cast(int, x.position),
                )
                exercises: list[PostWorkoutsRequestExercise] = []
                used_exercises: list[HevyAppExercise] = []
                for item in tqdm(workout_items):
                    note = None
                    exercise = item.exercise
                    tc_item = item.true_coach
                    if tc_item is None or tc_item.state != "completed":
                        continue
                    if isinstance(exercise, Exercise):
                        hevy_raw: object = exercise.hevy_app
                        if isinstance(hevy_raw, HevyAppExercise):
                            hevy_app_exercise = hevy_raw
                        else:
                            hevy_app_exercise = placeholder_exercises.pop(0)
                            if hevy_app_exercise.name != "#####PLACEHOLDER#####":
                                uow.tracker_add_exercise(exercise)
                    else:
                        hevy_app_exercise = placeholder_exercises.pop(0)

                    pos_meta = order.get(item.position, {})
                    is_superset = bool(pos_meta.get("is_superset"))
                    sg = pos_meta.get("superset_group")
                    if superset_index and is_superset and isinstance(sg, str):
                        super_set = superset_index.get(sg)
                    else:
                        super_set = None

                    if hevy_app_exercise.name != "#####PLACEHOLDER#####":
                        sets = self.get_sets(item.sets)
                    else:
                        note = str(tc_item.name or "")
                        sets = [
                            PostWorkoutsRequestSet(**s.model_dump())
                            for s in self._set_parser.parse_the_sets(
                                info=str(
                                    {
                                        "exercise_type": cast(str, hevy_app_exercise.type),
                                        "info": tc_item.info,
                                    }
                                )
                            ).sets
                        ]
                        if not sets:
                            sets = [
                                PostWorkoutsRequestSet(**s.model_dump())
                                for s in utils.parse_sets(str(tc_item.info or ""))
                            ]

                    exercises.append(
                        PostWorkoutsRequestExercise(
                            notes=note,
                            exercise_template_id=str(hevy_app_exercise.id),
                            superset_id=super_set,
                            sets=sets,
                        )
                    )
                    used_exercises.append(hevy_app_exercise)

                due_s = tc_workout.due.strftime("%d %b %Y") if tc_workout.due is not None else ""
                workout_request = PostWorkoutsRequestBody(
                    workout=PostWorkoutsRequest(
                        title=f"{due_s}\n{workout.title}\n{workout.true_coach_id}",
                        start_time=workout.start_date.isoformat()
                        if workout.start_date is not None
                        else "",
                        end_time=workout.end_date.isoformat()
                        if workout.end_date is not None
                        else "",
                        exercises=exercises,
                    )
                )

                self._workout_writer.create_workout(workout_request)

    def get_sets(self, sets: list[Sets]) -> list[PostWorkoutsRequestSet]:
        """Map tracker sets to Hevy POST set payloads.

        Args:
            sets (list[Sets]): Tracker ORM set rows.

        Returns:
            list[PostWorkoutsRequestSet]: Body for ``workouts.create``.
        """
        return [
            PostWorkoutsRequestSet(
                type=_coerce_set_type(cast(str, item.type)),
                weight_kg=cast(float | None, item.weight_kg),
                reps=cast(int | None, item.reps),
                distance_meters=cast(int | None, item.distance_meters),
                duration_seconds=cast(int | None, item.duration_seconds),
            )
            for item in sets
        ]
