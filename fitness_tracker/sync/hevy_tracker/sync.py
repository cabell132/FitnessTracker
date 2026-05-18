"""Sync Hevy workouts into the internal tracker and link True Coach IDs."""

from datetime import datetime
from typing import cast

from fitness_tracker.apis import HevyAppClient
from fitness_tracker.apis.hevy_app.types import (
    DeletedWorkout,
    Exercise as HevyAppExercise,
    UpdatedWorkout,
    Workout,
)
from fitness_tracker.database import Store
from fitness_tracker.database.models import TrueCoachExercise
from fitness_tracker.database.uow import UnitOfWork
from fitness_tracker.llm.fitness_llm import FitnessLLM
from logs import WideEvent


def _parse_api_datetime(value: str) -> datetime:
    """Parse ISO-like timestamps from Hevy API strings.

    Args:
        value (str): Timestamp string from Hevy (may end with ``Z``).

    Returns:
        datetime: Parsed timezone-aware or naive datetime.
    """
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


class HevyToFitnessTrackerSyncronizer:
    """Incremental Hevy → tracker sync with True Coach ID extraction and SQL linking."""

    def __init__(self, store: Store, source: HevyAppClient, llm: FitnessLLM) -> None:
        """Initiate the syncronizer with the clients.

        Args:
            store (Store): Persistence layer.
            source (HevyAppClient): Hevy API client for events.
            llm (FitnessLLM): LLM for fuzzy workout item linking.
        """
        self._store = store
        self._source = source
        self._llm = llm

    def update_workout(self, uow: UnitOfWork, workout: UpdatedWorkout) -> None:
        """Update the tracker row and link SQL for a Hevy workout update event.

        Args:
            uow (UnitOfWork): Active unit of work.
            workout (UpdatedWorkout): Hevy workout event payload.
        """
        with WideEvent(
            operation="update_workout",
            sync_source="hevy",
            sync_target="tracker",
            workout_id=workout.workout.id,
        ) as event:
            uow.hevy_add_workout(
                workout.workout,
                exercise_template_source=self._source.exercises,
            )
            true_coach_id = self.link_workout(uow, workout.workout.id, workout.workout)
            event.set(true_coach_id=true_coach_id)
            uow.flush()
            if true_coach_id:
                self.link_workout_items(uow, true_coach_id)
                self.update_exercise(uow, true_coach_id)
                self.update_sets(uow, true_coach_id)
                self.insert_sets(uow, true_coach_id)
                self.update_exercises(uow, true_coach_id)
            self.update_metrics(uow)

    def delete_workout(self, uow: UnitOfWork, event: DeletedWorkout) -> None:
        """Delete a Hevy-linked workout in the tracker.

        Args:
            uow (UnitOfWork): Active unit of work.
            event (DeletedWorkout): Deletion event from Hevy.
        """
        uow.hevy_delete_workout(id=event.id)

    def link_workout(
        self,
        uow: UnitOfWork,
        workout_id: str,
        workout: Workout,
    ) -> int | None:
        """Resolve True Coach workout id embedded in the Hevy title and link IDs.

        Args:
            uow (UnitOfWork): Active unit of work.
            workout_id (str): Hevy workout id.
            workout (Workout): Hevy workout payload containing the title tail id.

        Returns:
            int | None: Parsed True Coach workout id when valid digits were found.
        """
        true_coach_id = workout.title.split("\n")[-1]
        if not true_coach_id.isdigit():
            true_coach_id = workout.title.split(" ")[-1]
            if not true_coach_id.isdigit():
                return None

        tr_workout = uow.tracker_get_workout(true_coach_id=int(true_coach_id))
        if tr_workout:
            tr_workout.hevy_app_id = workout_id
            tr_workout.start_date = _parse_api_datetime(workout.start_time)
            tr_workout.end_date = _parse_api_datetime(workout.end_time)
            uow.merge(tr_workout)
        return int(true_coach_id)

    def link_workout_items(self, uow: UnitOfWork, true_coach_id: int) -> None:
        """Link Hevy and True Coach workout items using SQL plus LLM suggestions.

        Args:
            uow (UnitOfWork): Active unit of work.
            true_coach_id (int): True Coach workout id being linked.
        """
        uow.link_hevy_tracker_workout_items(true_coach_id)
        uow.flush()

        true_coach_items = uow.get_unlinked_tc_workout_items(true_coach_id)
        hevy_items = uow.get_unlinked_hevy_workout_items(true_coach_id)

        link_list = self._llm.link_workout_items(
            hevy_items=hevy_items,
            true_coach_items=true_coach_items,
        )

        for link in link_list.links:
            if link.hevy_app_id is None or link.true_coach_id is None:
                continue
            uow.link_workout_item_hevy_id(link.true_coach_id, link.hevy_app_id)
        uow.flush()

    def update_exercise(self, uow: UnitOfWork, true_coach_id: int) -> None:
        """Update tracker exercise ids from linked Hevy items.

        Args:
            uow (UnitOfWork): Active unit of work.
            true_coach_id (int): True Coach workout id scope.
        """
        uow.update_workout_exercise_ids_from_hevy(true_coach_id)

    def update_sets(self, uow: UnitOfWork, true_coach_id: int) -> None:
        """Run SQL to refresh set rows for a workout.

        Args:
            uow (UnitOfWork): Active unit of work.
            true_coach_id (int): True Coach workout id scope.
        """
        uow.update_hevy_tracker_sets(true_coach_id)

    def insert_sets(self, uow: UnitOfWork, true_coach_id: int) -> None:
        """Insert missing set rows from Hevy data.

        Args:
            uow (UnitOfWork): Active unit of work.
            true_coach_id (int): True Coach workout id scope.
        """
        uow.insert_hevy_tracker_sets(true_coach_id)

    def update_exercises(self, uow: UnitOfWork, true_coach_id: int) -> None:
        """Bulk-update exercise associations for a workout.

        Args:
            uow (UnitOfWork): Active unit of work.
            true_coach_id (int): True Coach workout id scope.
        """
        uow.update_hevy_tracker_exercises(true_coach_id)

    def link_exercises(
        self,
        uow: UnitOfWork,
        true_coach_id: int,
        hevy_exercises: list[HevyAppExercise],
    ) -> None:
        """Align Hevy exercises with True Coach items by workout ordering.

        Args:
            uow (UnitOfWork): Active unit of work.
            true_coach_id (int): True Coach workout id.
            hevy_exercises (list[HevyAppExercise]): Exercises from the Hevy workout.
        """
        true_coach_workout_items = uow.tc_get_workout_items(workout_id=true_coach_id)
        true_coach_workout_items.sort(
            key=lambda x: cast(int, x.position) if x.position is not None else 0,
        )
        true_coach_exercises = [
            ex for item in true_coach_workout_items if (ex := item.exercise) is not None
        ]

        for hevy_exercise in hevy_exercises:
            self.link_exercise(uow, true_coach_exercises, hevy_exercise)

    def link_exercise(
        self,
        uow: UnitOfWork,
        true_coach_exercises: list[TrueCoachExercise],
        hevy_exercise: HevyAppExercise,
        _threshold: int = 90,
    ) -> None:
        """Link a single Hevy exercise to the tracker by index order.

        Args:
            uow (UnitOfWork): Active unit of work.
            true_coach_exercises (list[TrueCoachExercise]): Ordered True Coach exercises.
            hevy_exercise (HevyAppExercise): Hevy block from the workout payload.
            _threshold (int, optional): Reserved for future fuzzy match cutoff.
        """
        instance = uow.tracker_get_exercise(
            hevy_app_id=hevy_exercise.exercise_template_id,
        )
        if instance and instance.true_coach_id:
            return

        idx = hevy_exercise.index
        if idx < 0 or idx >= len(true_coach_exercises):
            return
        best_match = true_coach_exercises[idx]

        instance = uow.tracker_get_exercise(true_coach_id=best_match.id)
        if instance:
            instance.hevy_app_id = hevy_exercise.exercise_template_id
            uow.merge(instance)

    def sync_events(self, events: list[UpdatedWorkout | DeletedWorkout]) -> None:
        """Apply Hevy workout events to the database in batch.

        Args:
            events (list[UpdatedWorkout | DeletedWorkout]): Ordered Hevy events.
        """
        with self._store.unit_of_work() as uow:
            for event in events:
                if isinstance(event, UpdatedWorkout):
                    self.update_workout(uow, event)
                elif isinstance(event, DeletedWorkout):
                    self.delete_workout(uow, event)

    def sync_workouts(self, since: datetime) -> list[UpdatedWorkout | DeletedWorkout]:
        """Fetch and apply Hevy workout events since a timestamp.

        Args:
            since (datetime): Lower bound for the Hevy events query.

        Returns:
            list[UpdatedWorkout | DeletedWorkout]: Events applied (oldest first).
        """
        with WideEvent(
            operation="sync_workouts",
            sync_source="hevy",
            sync_target="tracker",
        ) as evt:
            res = self._source.workouts.get_workout_events(since=since)
            if res:
                if res.page_count > 1:
                    for page in range(2, res.page_count + 1):
                        new_res = self._source.workouts.get_workout_events(
                            since=since,
                            page=page,
                        )
                        if new_res:
                            for event in new_res.events:
                                res.events.append(event)

                evt.set(event_count=len(res.events))
                self.sync_events(res.events[::-1])

                return res.events[::-1]
            evt.set(event_count=0)
            return []

    def update_metrics(self, uow: UnitOfWork) -> None:
        """Insert calorie metrics derived from Hevy sync.

        Args:
            uow (UnitOfWork): Active unit of work.
        """
        uow.insert_hevy_calories_burned_metrics()
