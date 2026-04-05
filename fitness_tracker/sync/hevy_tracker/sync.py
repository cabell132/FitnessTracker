"""Sync Hevy workouts into the internal tracker and link True Coach IDs."""

from datetime import datetime
from pathlib import Path
from typing import cast

from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from fitness_tracker.apis import HevyAppClient
from fitness_tracker.apis.hevy_app.types import (
    DeletedWorkout,
    Exercise as HevyAppExercise,
    UpdatedWorkout,
    Workout,
)
from fitness_tracker.database import Database
from fitness_tracker.database.models import TrueCoachExercise
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

    def __init__(self, database: Database, source: HevyAppClient, llm: FitnessLLM) -> None:
        """Initiate the syncronizer with the clients.

        Args:
            database (Database): Persistence layer.
            source (HevyAppClient): Hevy API client for events.
            llm (FitnessLLM): LLM for fuzzy workout item linking.
        """
        self._database = database
        self._source = source
        self._llm = llm

    def update_workout(self, session: Session, workout: UpdatedWorkout) -> None:
        """Update the tracker row and link SQL for a Hevy workout update event.

        Args:
            session (Session): SQLAlchemy session.
            workout (UpdatedWorkout): Hevy workout event payload.
        """
        with WideEvent(
            operation="update_workout",
            sync_source="hevy",
            sync_target="tracker",
            workout_id=workout.workout.id,
        ) as event:
            self._database.hevy_app.add_workout(session, workout.workout)
            true_coach_id = self.link_workout(session, workout.workout.id, workout.workout)
            event.set(true_coach_id=true_coach_id)
            session.commit()
            if true_coach_id:
                self.link_workout_items(session, true_coach_id)
                self.update_exercise(session, true_coach_id)
                self.update_sets(session, true_coach_id)
                self.insert_sets(session, true_coach_id)
                self.update_exercises(session, true_coach_id)
            self.update_metrics(session)

    def delete_workout(self, session: Session, event: DeletedWorkout) -> None:
        """Delete a Hevy-linked workout in the tracker.

        Args:
            session (Session): SQLAlchemy session.
            event (DeletedWorkout): Deletion event from Hevy.
        """
        self._database.hevy_app.delete_workout(session, id=event.id)

    def link_workout(self, session: Session, workout_id: str, workout: Workout) -> int | None:
        """Resolve True Coach workout id embedded in the Hevy title and link IDs.

        Args:
            session (Session): SQLAlchemy session.
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

        tr_workout = self._database.tracker.get_workout(session, true_coach_id=int(true_coach_id))
        if tr_workout:
            tr_workout.hevy_app_id = workout_id
            tr_workout.start_date = _parse_api_datetime(workout.start_time)
            tr_workout.end_date = _parse_api_datetime(workout.end_time)

            session.merge(tr_workout)
        return int(true_coach_id)

    def link_workout_items(self, session: Session, true_coach_id: int) -> None:
        """Link Hevy and True Coach workout items using SQL plus LLM suggestions.

        Args:
            session (Session): SQLAlchemy session.
            true_coach_id (int): True Coach workout id being linked.
        """
        insert_script = text(
            Path("fitness_tracker/database/SQL/hevy/tracker/workout_items/update.sql").read_text(
                encoding="utf-8"
            )
        )
        session.execute(insert_script, {"true_coach_id": true_coach_id})
        session.commit()

        stmnt = text("""
                    SELECT tcwi.id as true_coach_id, tcwi.name, tcwi.position as 'order'
                    FROM WorkoutItem as wi
                    JOIN Workout w ON wi.workout_id = w.id
                    JOIN TrueCoachWorkoutItem tcwi ON wi.true_coach_id = tcwi.id
                    WHERE w.true_coach_id = :true_coach_id
                    AND wi.hevy_app_id IS NULL
                    """)
        res = session.execute(stmnt, {"true_coach_id": true_coach_id}).fetchall()
        true_coach_items = [row._asdict() for row in res]

        stmnt = text("""
                    SELECT hwi.id as hevy_app_id, hwi.name, hwi."index" + 1 as "order"
                    FROM HevyAppWorkoutItem as hwi
                    JOIN HevyAppWorkout hw  ON hw.id = hwi.workout_id
                    JOIN Workout w ON w.hevy_app_id = hw.id
                    WHERE w.true_coach_id = :true_coach_id
                    AND hwi.id NOT IN (
                        SELECT hevy_app_id
                        FROM WorkoutItem
                        WHERE workout_id = w.id
                        AND hevy_app_id IS NOT NULL
                        )""")
        res = session.execute(stmnt, {"true_coach_id": true_coach_id}).fetchall()
        hevy_items = [row._asdict() for row in res]

        link_list = self._llm.link_workout_items(
            hevy_items=hevy_items, true_coach_items=true_coach_items
        )

        for link in link_list.links:
            if link.hevy_app_id is None:
                continue
            stmnt = text("""
                        UPDATE WorkoutItem
                        SET hevy_app_id = :hevy_app_id
                        WHERE true_coach_id = :true_coach_id
                        """)
            session.execute(stmnt, link.model_dump())
        session.commit()

    def update_exercise(self, session: Session, true_coach_id: int) -> None:
        """Update tracker exercise ids from linked Hevy items.

        Args:
            session (Session): SQLAlchemy session.
            true_coach_id (int): True Coach workout id scope.
        """
        stmnt = text("""
                    UPDATE WorkoutItem
                    SET exercise_id = (
                        SELECT e.id
                        FROM HevyAppWorkoutItem hwi
                        JOIN Exercise e ON hwi.exercise_id = e.hevy_app_id
                        JOIN WorkoutItem wi ON wi.hevy_app_id = hwi.id
                        JOIN Workout w ON w.id = wi.workout_id
                        WHERE WorkoutItem.id = wi.id
                        AND e.id IS NOT NULL
                        AND w.true_coach_id = :true_coach_id
                        LIMIT 1
                    )
                    WHERE EXISTS (
                        SELECT 1
                        FROM HevyAppWorkoutItem hwi
                        JOIN Exercise e ON hwi.exercise_id = e.hevy_app_id
                        JOIN WorkoutItem wi ON wi.hevy_app_id = hwi.id
                        JOIN Workout w ON w.id = wi.workout_id
                        WHERE WorkoutItem.id = wi.id
                        AND e.id IS NOT NULL
                        AND e.id != wi.exercise_id
                        AND w.true_coach_id = :true_coach_id
                    );
                        """)
        session.execute(stmnt, {"true_coach_id": true_coach_id})
        session.commit()

    def update_sets(self, session: Session, true_coach_id: int) -> None:
        """Run SQL to refresh set rows for a workout.

        Args:
            session (Session): SQLAlchemy session.
            true_coach_id (int): True Coach workout id scope.
        """
        stmnt = text(
            Path("fitness_tracker/database/SQL/hevy/tracker/sets/update.sql").read_text(
                encoding="utf-8"
            )
        )
        session.execute(stmnt, {"true_coach_id": true_coach_id})
        session.commit()

    def insert_sets(self, session: Session, true_coach_id: int) -> None:
        """Insert missing set rows from Hevy data.

        Args:
            session (Session): SQLAlchemy session.
            true_coach_id (int): True Coach workout id scope.
        """
        stmnt = text(
            Path("fitness_tracker/database/SQL/hevy/tracker/sets/insert.sql").read_text(
                encoding="utf-8"
            )
        )
        session.execute(stmnt, {"true_coach_id": true_coach_id})
        session.commit()

    def update_exercises(self, session: Session, true_coach_id: int) -> None:
        """Bulk-update exercise associations for a workout.

        Args:
            session (Session): SQLAlchemy session.
            true_coach_id (int): True Coach workout id scope.
        """
        stmnt = text(
            Path("fitness_tracker/database/SQL/hevy/tracker/exercises/update.sql").read_text(
                encoding="utf-8"
            )
        )
        session.execute(stmnt, {"true_coach_id": true_coach_id})
        session.commit()

    def link_exercises(
        self, session: Session, true_coach_id: int, hevy_exercises: list[HevyAppExercise]
    ) -> None:
        """Align Hevy exercises with True Coach items by workout ordering.

        Args:
            session (Session): SQLAlchemy session.
            true_coach_id (int): True Coach workout id.
            hevy_exercises (list[HevyAppExercise]): Exercises from the Hevy workout.
        """
        true_coach_workout_items = self._database.true_coach.get_workout_items(
            session, workout_id=true_coach_id
        )
        true_coach_workout_items.sort(
            key=lambda x: cast(int, x.position) if x.position is not None else 0,
        )
        true_coach_exercises = [
            ex for item in true_coach_workout_items if (ex := item.exercise) is not None
        ]

        for hevy_exercise in hevy_exercises:
            self.link_exercise(session, true_coach_exercises, hevy_exercise)

    def link_exercise(
        self,
        session: Session,
        true_coach_exercises: list[TrueCoachExercise],
        hevy_exercise: HevyAppExercise,
        _threshold: int = 90,
    ) -> None:
        """Link a single Hevy exercise to the tracker by index order.

        Args:
            session (Session): SQLAlchemy session.
            true_coach_exercises (list[TrueCoachExercise]): Ordered True Coach exercises.
            hevy_exercise (HevyAppExercise): Hevy block from the workout payload.
            _threshold (int, optional): Reserved for future fuzzy match cutoff. Defaults to 90.
        """
        instance = self._database.tracker.get_exercise(
            session, hevy_app_id=hevy_exercise.exercise_template_id
        )
        if instance and instance.true_coach_id:
            return

        idx = hevy_exercise.index
        if idx < 0 or idx >= len(true_coach_exercises):
            return
        best_match = true_coach_exercises[idx]

        instance = self._database.tracker.get_exercise(session, true_coach_id=best_match.id)
        if instance:
            instance.hevy_app_id = hevy_exercise.exercise_template_id
            session.merge(instance)

    def sync_events(self, events: list[UpdatedWorkout | DeletedWorkout]) -> None:
        """Apply Hevy workout events to the database in batch.

        Args:
            events (list[UpdatedWorkout | DeletedWorkout]): Ordered Hevy events.
        """
        with self._database.hevy_app.get_session() as session:
            for event in events:
                if isinstance(event, UpdatedWorkout):
                    self.update_workout(session, event)
                elif isinstance(event, DeletedWorkout):
                    self.delete_workout(session, event)

            session.commit()

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

    def update_metrics(self, session: Session) -> None:
        """Insert calorie metrics derived from Hevy sync.

        Args:
            session (Session): SQLAlchemy session.
        """
        stmnt = text(
            Path(
                "fitness_tracker/database/SQL/hevy/tracker/metric/calories_burned/insert.sql"
            ).read_text(encoding="utf-8")
        )
        session.execute(stmnt)
        session.commit()
