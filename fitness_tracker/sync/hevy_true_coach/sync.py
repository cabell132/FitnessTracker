"""Push completed Hevy workouts to True Coach workout items."""

from __future__ import annotations

from typing import cast

from fitness_tracker.apis import TrueCoachClient
from fitness_tracker.apis.hevy_app.types import Set as HevySet
from fitness_tracker.apis.true_coach.types import PutWorkoutItemRequest
from fitness_tracker.database import Database
from fitness_tracker.database.models import (
    HevyAppExercise,
    HevyAppWorkout,
    HevyAppWorkoutItem,
    TrueCoachWorkoutItem,
)
from fitness_tracker.sync.hevy_true_coach.utils import mapping
from logs import WideEvent


class HevyToTrueCoachSyncronizer:
    """Updates True Coach items when a linked Hevy workout is completed."""

    def __init__(self, database: Database, target: TrueCoachClient) -> None:
        """Initiate the syncronizer with the clients.

        Args:
            database (Database): Database access for Hevy and True Coach ORM rows.
            target (TrueCoachClient): API client for True Coach mutations.
        """
        self._database = database
        self._target = target

    def sync_workout(self, hevy_workout_id: str) -> None:  # noqa: PLR0915
        """Mark matching True Coach items complete from a Hevy workout.

        Args:
            hevy_workout_id (str): Hevy workout primary key.

        Raises:
            TypeError: If the Hevy workout or linked True Coach workout is missing.
            ValueError: If Hevy/True Coach item pairing is inconsistent.
        """
        with (
            WideEvent(
                operation="sync_workout",
                sync_source="hevy",
                sync_target="true_coach",
                hevy_workout_id=hevy_workout_id,
            ) as evt,
            self._database.hevy_app.get_session() as session,
        ):
            hevy_app_workout = self._database.hevy_app.get_workout(
                session,
                id=hevy_workout_id,
            )
            if not isinstance(hevy_app_workout, HevyAppWorkout):
                msg = f"Workout with id {hevy_workout_id} not found"
                raise TypeError(msg)

            true_coach_workout = hevy_app_workout.true_coach
            if not true_coach_workout:
                msg = f"True coach workout not found for workout with id {hevy_workout_id}"
                raise TypeError(msg)

            hevy_app_workout_items: list[HevyAppWorkoutItem] = list(
                hevy_app_workout.workout_items,
            )
            items_synced = 0
            items_skipped = 0

            for item in hevy_app_workout_items:
                exercise = item.exercise
                if isinstance(exercise, HevyAppExercise):
                    exercise_type = cast(str, exercise.type)
                    if exercise_type not in mapping:
                        msg = f"Exercise type {exercise_type} is not supported yet"
                        raise ValueError(msg)
                    formatter = mapping[exercise_type]
                    sets_payload = cast(list[HevySet], item.sets)
                    result = formatter(sets_payload)

                    true_coach_workout_item = item.true_coach
                    if isinstance(true_coach_workout_item, TrueCoachWorkoutItem):
                        tc_pos = cast(int | None, true_coach_workout_item.position)
                        info = str(true_coach_workout_item.info or "")
                        update_workout_item = PutWorkoutItemRequest(
                            id=cast(int, true_coach_workout_item.id),
                            workout_id=cast(int, true_coach_workout_item.workout_id),
                            name=cast(str, true_coach_workout_item.name),
                            info=info,
                            result=result.strip(),
                            is_circuit=cast(bool, true_coach_workout_item.is_circuit),
                            state="completed",
                            state_event="mark_as_completed",
                            position=tc_pos if tc_pos is not None else 0,
                            exercise_id=cast(
                                int | None,
                                true_coach_workout_item.exercise_id,
                            ),
                            assessment_id=cast(
                                int | None,
                                true_coach_workout_item.assessment_id,
                            ),
                        )

                        self._target.workouts.update_workout_item(
                            update_workout_item.id,
                            update_workout_item,
                        )

                        self._database.true_coach.update_workout_item(
                            session,
                            update_workout_item,
                        )
                        items_synced += 1
                    else:
                        items_skipped += 1

            self._target.workouts.mark_as_completed(cast(int, true_coach_workout.id))
            evt.set(
                item_count=len(hevy_app_workout_items),
                items_synced=items_synced,
                items_skipped=items_skipped,
            )
            session.commit()
