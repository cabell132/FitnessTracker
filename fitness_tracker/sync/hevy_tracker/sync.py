from datetime import datetime
from pathlib import Path
from typing import Optional

from fitness_tracker.apis import HevyAppClient
from fitness_tracker.apis.hevy_app.types import DeletedWorkout, UpdatedWorkout, Workout
from fitness_tracker.apis.hevy_app.types import Exercise as HevyAppExercise
from fitness_tracker.database import Database
from fitness_tracker.database.models import TrueCoachExercise
from fitness_tracker.llm.fitness_llm import FitnessLLM
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from dateutil.parser import parse


class HevyToFitnessTrackerSyncronizer:
    """Syncronizer class"""

    def __init__(self, database: Database, source: HevyAppClient, llm: FitnessLLM) -> None:
        """Initiate the syncronizer with the clients."""
        self._database = database
        self._source = source
        self._llm = llm

    def update_workout(self, session: Session, workout: UpdatedWorkout) -> None:
        """Update the workout with the given id.

        Args:
            workout_id (int): The workout id to syncronize

        """
        self._database.hevy_app.add_workout(session, workout.workout)
        true_coach_id = self.link_workout(session, workout.workout.id, workout.workout)
        print(f"True Coach ID for workout {workout.workout.id} is {true_coach_id}")
        session.commit()
        if true_coach_id:
            self.link_workout_items(session, true_coach_id)
            self.update_exercise(session, true_coach_id)
            self.update_sets(session, true_coach_id)
            self.insert_sets(session, true_coach_id)
            self.update_exercises(session, true_coach_id)
        else:
            print(f"Could not find True Coach ID for workout {workout.workout.id}")


        self.update_metrics(session)

    def delete_workout(self, session: Session, event: DeletedWorkout) -> None:
        """Delete the workout with the given id.

        Args:
            workout_id (int): The workout id to syncronize

        """
        self._database.hevy_app.delete_workout(session, id=event.id)

    def link_workout(
        self, session: Session, workout_id: str, workout: Workout
    ) -> Optional[int]:
        """Get the linked workout.

        Args:
            session (Session): The session to use
            workout_id (str): The Hevy workout id to get the linked workout
            workout_description (str): The workout description to get the linked workout

        """
        true_coach_id = workout.title.split("\n")[-1]
        print(true_coach_id)
        if not true_coach_id.isdigit():
            true_coach_id = workout.title.split(" ")[-1]
            if not true_coach_id.isdigit():
                return None

        tr_workout = self._database.tracker.get_workout(session, true_coach_id=int(true_coach_id))
        if tr_workout:
            tr_workout.hevy_app_id = workout_id  # type: ignore
            tr_workout.start_date=parse(workout.start_time) # type: ignore
            tr_workout.end_date=parse(workout.end_time) # type: ignore

            session.merge(tr_workout)  # type: ignore
        return int(true_coach_id)

    def link_workout_items(self, session: Session, true_coach_id: int) -> None:
        """Link the exercises.

        Args:
            session (Session): The session to use
            true_coach_id (int): The True Coach workout id
            hevy_exercises (list[HevyAppExercise]): The Hevy App exercises

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
        """Update the exercise with the given id.

        Args:
            session (Session): The session to use
            true_coach_id (int): The True Coach exercise id to syncronize

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
        session.execute(stmnt, {"true_coach_id": true_coach_id})  # type: ignore
        session.commit()

    def update_sets(self, session: Session, true_coach_id: int) -> None:
        """Update the sets with the given id.

        Args:
            session (Session): The session to use
            true_coach_id (int): The True Coach exercise id to syncronize

        """
        stmnt = text(
            Path("fitness_tracker/database/SQL/hevy/tracker/sets/update.sql").read_text(
                encoding="utf-8"
            )
        )
        session.execute(stmnt, {"true_coach_id": true_coach_id})
        session.commit()

    def insert_sets(self, session: Session, true_coach_id: int) -> None:
        """Insert the sets with the given id.

        Args:
            session (Session): The session to use
            true_coach_id (int): The True Coach exercise id to syncronize

        """
        stmnt = text(
            Path("fitness_tracker/database/SQL/hevy/tracker/sets/insert.sql").read_text(
                encoding="utf-8"
            )
        )
        session.execute(stmnt, {"true_coach_id": true_coach_id})
        session.commit()

    def update_exercises(self, session: Session, true_coach_id: int) -> None:
        """Update the exercises.

        Args:
            session (Session): The session to use
            true_coach_id (int): The True Coach workout id

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
        """Link the exercises.

        Args:
            session (Session): The session to use
            true_coach_id (int): The True Coach workout id
            hevy_exercises (list[HevyAppExercise]): The Hevy App exercises

        """
        true_coach_workout_items = self._database.true_coach.get_workout_items(
            session, workout_id=true_coach_id
        )
        # sort workout items by position
        true_coach_workout_items.sort(key=lambda x: x.position)  # type: ignore
        true_coach_exercises = [item.exercise for item in true_coach_workout_items]

        for hevy_exercise in hevy_exercises:
            self.link_exercise(session, true_coach_exercises, hevy_exercise)

    def link_exercise(
        self,
        session: Session,
        true_coach_exercises: list[TrueCoachExercise],
        hevy_exercise: HevyAppExercise,
        threshold: int = 90,
    ) -> None:
        """Link the exercises.

        Args:
            session (Session): The session to use
            true_coach_exercises (list[TrueCoachExercise]): The True Coach exercises
            hevy_exercise (HevyAppExercise): The Hevy App exercise

        """
        instance = self._database.tracker.get_exercise(
            session, hevy_app_id=hevy_exercise.exercise_template_id
        )
        if instance:
            if instance.true_coach_id:
                print(f"Exercise {hevy_exercise.title} has a true_coach_id")
                return

        # best_match = None
        # best_score = 0
        # for true_coach_exercise in true_coach_exercises:
        #     score = fuzz.WRatio(str(true_coach_exercise.name), str(hevy_exercise.title))
        #     if score > best_score:
        #         best_score = score
        #         best_match = true_coach_exercise
        # print(f"Best match for {hevy_exercise.title} is {best_match.name} with score {best_score}")
        # if best_score < threshold:
        #     return

        best_match = true_coach_exercises[hevy_exercise.index]
        if not best_match:
            return

        instance = self._database.tracker.get_exercise(session, true_coach_id=best_match.id)
        if instance:
            instance.hevy_app_id = hevy_exercise.exercise_template_id
            session.merge(instance)

    def sync_events(self, events: list[UpdatedWorkout | DeletedWorkout]) -> None:
        """Syncronize the events

        Args:
            events (list[UpdatedWorkout | DeletedWorkout]): The events to syncronize

        """
        with self._database.hevy_app.get_session() as session:
            for event in events:
                if isinstance(event, UpdatedWorkout):
                    self.update_workout(session, event)
                elif isinstance(event, DeletedWorkout):  # type: ignore
                    self.delete_workout(session, event)

            session.commit()

    def sync_workouts(self, since: datetime) -> list[UpdatedWorkout | DeletedWorkout]:
        """Syncronize the workout with the given id.

        Args:
            since (datetime): The datetime to syncronize

        """
        res = self._source.workouts.get_workout_events(since=since)
        if res:
            if res.page_count > 1:
                for page in range(2, res.page_count + 1):
                    new_res = self._source.workouts.get_workout_events(since=since, page=page)
                    if new_res:
                        for event in new_res.events:
                            res.events.append(event)

            self.sync_events(res.events[::-1])

            return res.events[::-1]
        return []

    def update_metrics(self, session: Session) -> None:
        """Update the metrics with the given id.

        Args:
            session (Session): The session to use
            metrics (list[UpdatedWorkout | DeletedWorkout]): The metrics to syncronize

        """
        stmnt = text(
                Path("fitness_tracker/database/SQL/hevy/tracker/metric/calories_burned/insert.sql").read_text(
                    encoding="utf-8"
                )
            )
        session.execute(stmnt) # type: ignore
        session.commit()
