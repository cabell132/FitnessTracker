"""Fitness tracker (canonical) database service."""

from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from fitness_tracker.database.models import TrueCoachExercise, TrueCoachWorkout
from fitness_tracker.database.models.tracker import Exercise, Workout, WorkoutItem
from fitness_tracker.database.repository.tracker import (
    FitnessTrackerExerciseRepository,
    FitnessTrackerWorkoutRepository,
    FitnessTrackerWorkoutItemRepository,
)
from fitness_tracker.database.services.base import BaseService


class FitnessTrackerService(BaseService):
    """Read/write helpers for unified tracker workout and exercise tables."""

    def __init__(self, engine: Engine) -> None:
        """Create the service bound to the given engine.

        Args:
            engine (Engine): SQLAlchemy engine for the tracker database.
        """
        super().__init__(engine)

    def add_workout(self, session: Session, workout: TrueCoachWorkout) -> None:
        """Insert a canonical workout row linked from a True Coach workout.

        Args:
            session (Session): Active session.
            workout (TrueCoachWorkout): Source row to mirror.

        Returns:
            None: Nothing is returned.
        """
        workout_repo = FitnessTrackerWorkoutRepository(session=session)

        instance = Workout(
            title=workout.title,
            description=workout.short_description,
            true_coach_id=workout.id,
        )
        workout_repo.insert_ignore(instance)

    def get_workout(self, session: Session, **kwargs: Any) -> Workout | None:
        """Fetch a workout by arbitrary filter kwargs.

        Args:
            session (Session): Active session.
            **kwargs (Any): Column filters passed to the repository.

        Returns:
            Workout | None: Matching row if any.
        """
        workout_repo = FitnessTrackerWorkoutRepository(session=session)
        return workout_repo.get(**kwargs)

    def add_exercise(self, session: Session, exercise: TrueCoachExercise) -> None:
        """Ensure a canonical exercise exists and link it to True Coach ids.

        Args:
            session (Session): Active session.
            exercise (TrueCoachExercise): Source exercise row.

        Returns:
            None: Nothing is returned.
        """
        exercise_repo = FitnessTrackerExerciseRepository(session=session)
        if exercise_repo.get(true_coach_id=exercise.id):
            return

        existing = exercise_repo.get(name=exercise.name)
        if existing:
            existing.true_coach_id = exercise.id
            return

        entry = Exercise(
            name=exercise.name,
            true_coach_id=exercise.id,
        )

        exercise_repo.add(entry)

    def get_exercise(self, session: Session, **kwargs: Any) -> Exercise | None:
        """Fetch an exercise by arbitrary filter kwargs.

        Args:
            session (Session): Active session.
            **kwargs (Any): Column filters passed to the repository.

        Returns:
            Exercise | None: Matching row if any.
        """
        exercise_repo = FitnessTrackerExerciseRepository(session=session)
        return exercise_repo.get(**kwargs)

    def get_workout_item_by_index(
        self, session: Session, workout_id: int, index: int
    ) -> WorkoutItem | None:
        """Return the workout item for the given position within a workout.

        Args:
            session (Session): Active session.
            workout_id (int): Parent workout primary key.
            index (int): Item position within the workout (``WorkoutItem.position``).

        Returns:
            WorkoutItem | None: Matching row if any.
        """
        workout_item_repo = FitnessTrackerWorkoutItemRepository(session=session)
        return workout_item_repo.get(workout_id=workout_id, position=index)
