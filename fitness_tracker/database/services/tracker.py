from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from fitness_tracker.database.models import TrueCoachExercise, TrueCoachWorkout
from fitness_tracker.database.models.tracker import Exercise, Workout
from fitness_tracker.database.repository.tracker import (
    FitnessTrackerExerciseRepository,
    FitnessTrackerWorkoutRepository,
    FitnessTrackerSetsRepository,
    FitnessTrackerWorkoutItemRepository,
)
from fitness_tracker.database.services.base import BaseService


class FitnessTrackerService(BaseService):
    """Fitness Tracker database service class."""

    def __init__(self, engine: Engine) -> None:
        """Initiate the Hevy App service with the engine."""
        super().__init__(engine)

    def add_workout(self, session: Session, workout: TrueCoachWorkout):
        """Add a new workout."""
        workout_repo = FitnessTrackerWorkoutRepository(session=session)

        instance = Workout(
            title=workout.title,
            description=workout.short_description,
            true_coach_id=workout.id,
        )
        workout_repo.insert_ignore(instance)

    def get_workout(self, session: Session, **kwargs: Any):
        """Get a workout by kwargs."""
        workout_repo = FitnessTrackerWorkoutRepository(session=session)
        return workout_repo.get(**kwargs)

    def add_exercise(self, session: Session, exercise: TrueCoachExercise):
        """Add a new exercise."""
        exercise_repo = FitnessTrackerExerciseRepository(session=session)
        if exercise_repo.get(true_coach_id=exercise.id):
            return

        entry = Exercise(
            name=exercise.name,
            true_coach_id=exercise.id,
        )

        exercise_repo.add(entry)

    def get_exercise(self, session: Session, **kwargs: Any):
        """Get an exercise by kwargs."""
        exercise_repo = FitnessTrackerExerciseRepository(session=session)
        return exercise_repo.get(**kwargs)

    def get_workout_item_by_index(self, session: Session, workout_id: int, index: int):
        """Get a workout item by index."""
        workout_item_repo = FitnessTrackerWorkoutItemRepository(session=session)
        return workout_item_repo.get(index=index)
    
