"""Push completed Hevy workouts to True Coach workout items."""

from __future__ import annotations

from typing import cast

from fitness_tracker.apis import TrueCoachClient
from fitness_tracker.apis.hevy_app.types import Set as HevySet
from fitness_tracker.apis.true_coach.exceptions import TrueCoachAPIError
from fitness_tracker.apis.true_coach.types import (
    PutWorkoutItemRequest,
    Workout as TrueCoachWorkoutPayload,
    WorkoutItem as TrueCoachWorkoutItemPayload,
)
from fitness_tracker.database import Store
from fitness_tracker.database.models import (
    HevyAppExercise,
    HevyAppWorkout,
    HevyAppWorkoutItem,
    TrueCoachWorkoutItem,
)
from fitness_tracker.database.tx import Tx
from fitness_tracker.sync.hevy_true_coach.utils import mapping
from logs import WideEvent


class HevyToTrueCoachSyncronizer:
    """Updates True Coach items when a linked Hevy workout is completed."""

    def __init__(self, store: Store, target: TrueCoachClient) -> None:
        """Initiate the syncronizer with the clients.

        Args:
            store (Store): Persistence layer.
            target (TrueCoachClient): API client for True Coach mutations.
        """
        self._store = store
        self._target = target

    def _build_update_request(
        self,
        true_coach_workout_item: TrueCoachWorkoutItem,
        result: str,
    ) -> PutWorkoutItemRequest:
        """Build the PUT payload from the latest local True Coach row.

        Args:
            true_coach_workout_item (TrueCoachWorkoutItem): Local True Coach item row.
            result (str): Formatted workout result text.

        Returns:
            PutWorkoutItemRequest: API update payload.
        """
        tc_pos = cast(int | None, true_coach_workout_item.position)
        info = str(true_coach_workout_item.info or "")
        return PutWorkoutItemRequest(
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

    def _get_recent_true_coach_workout(
        self,
        workout_id: int,
    ) -> tuple[TrueCoachWorkoutPayload, list[TrueCoachWorkoutItemPayload]] | None:
        """Fetch the latest True Coach snapshot for one workout from recent pages.

        Args:
            workout_id (int): True Coach workout ID.

        Returns:
            tuple[TrueCoachWorkoutPayload, list[TrueCoachWorkoutItemPayload]] | None:
                Matching workout and items when found.
        """
        page = 1
        total_pages = 1
        while page <= total_pages:
            response = self._target.workouts.get(
                order="desc",
                page=page,
                per_page=100,
                states=["pending", "completed", "missed"],
            )
            if response is None:
                return None

            total_pages = response.meta.total_pages
            workout = next((w for w in response.workouts if w.id == workout_id), None)
            if workout is not None:
                items = [item for item in response.workout_items if item.workout_id == workout_id]
                return workout, items
            page += 1
        return None

    def _refresh_true_coach_workout(self, uow: Tx, workout_id: int) -> bool:
        """Repair stale local True Coach rows from the latest API snapshot.

        Args:
            uow (Tx): Active unit of work.
            workout_id (int): True Coach workout ID.

        Returns:
            bool: True when fresh API rows were found and stored.
        """
        latest = self._get_recent_true_coach_workout(workout_id)
        if latest is None:
            return False

        workout, workout_items = latest
        uow.true_coach.add_workout(workout)
        for workout_item in workout_items:
            uow.true_coach.add_workout_item(workout_item)
        uow.cross_domain.insert_tc_tracker_workout_items()
        uow.session.flush()
        uow.session.expire_all()
        return True

    def sync_workout(self, hevy_workout_id: str) -> None:  # noqa: C901, PLR0912, PLR0915
        """Mark matching True Coach items complete from a Hevy workout.

        Args:
            hevy_workout_id (str): Hevy workout primary key.

        Raises:
            TrueCoachAPIError: If True Coach update calls fail.
            TypeError: If the Hevy workout is missing.
            ValueError: If Hevy/True Coach item pairing is inconsistent.
        """
        with (
            WideEvent(
                operation="sync_workout",
                sync_source="hevy",
                sync_target="true_coach",
                hevy_workout_id=hevy_workout_id,
            ) as evt,
            self._store.unit_of_work() as uow,
        ):
            hevy_app_workout = uow.hevy.get_workout(id=hevy_workout_id)
            if not isinstance(hevy_app_workout, HevyAppWorkout):
                msg = f"Workout with id {hevy_workout_id} not found"
                raise TypeError(msg)

            true_coach_workout = hevy_app_workout.true_coach
            if not true_coach_workout:
                evt.set(
                    item_count=len(hevy_app_workout.workout_items),
                    items_synced=0,
                    items_skipped=len(hevy_app_workout.workout_items),
                    skipped_reason="missing_true_coach_workout",
                )
                return

            hevy_app_workout_item_ids = [
                cast(int, item.id) for item in hevy_app_workout.workout_items
            ]
            items_synced = 0
            items_skipped = 0
            repairs_applied = 0

            for item_id in hevy_app_workout_item_ids:
                item = uow.session.get(HevyAppWorkoutItem, id=item_id)
                if not isinstance(item, HevyAppWorkoutItem):
                    items_skipped += 1
                    continue
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
                        update_workout_item = self._build_update_request(
                            true_coach_workout_item,
                            result,
                        )
                        try:
                            self._target.workouts.update_workout_item(
                                update_workout_item.id,
                                update_workout_item,
                            )
                        except TrueCoachAPIError as exc:
                            if exc.status_code != 404:
                                raise
                            if not self._refresh_true_coach_workout(
                                uow,
                                cast(int, true_coach_workout.id),
                            ):
                                items_skipped += 1
                                continue
                            repairs_applied += 1
                            item = uow.session.get(HevyAppWorkoutItem, id=item_id)
                            if not isinstance(item, HevyAppWorkoutItem):
                                items_skipped += 1
                                continue
                            true_coach_workout_item = item.true_coach
                            if not isinstance(true_coach_workout_item, TrueCoachWorkoutItem):
                                items_skipped += 1
                                continue
                            update_workout_item = self._build_update_request(
                                true_coach_workout_item,
                                result,
                            )
                            self._target.workouts.update_workout_item(
                                update_workout_item.id,
                                update_workout_item,
                            )

                        uow.true_coach.update_workout_item(update_workout_item)
                        items_synced += 1
                    else:
                        items_skipped += 1

            self._target.workouts.mark_as_completed(cast(int, true_coach_workout.id))
            evt.set(
                item_count=len(hevy_app_workout_item_ids),
                items_synced=items_synced,
                items_skipped=items_skipped,
                repairs_applied=repairs_applied,
            )
