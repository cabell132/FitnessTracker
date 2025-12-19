from typing import Any

from dateutil.parser import parse
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from fitness_tracker.apis.hevy_app import HevyAppClient
from fitness_tracker.apis.hevy_app.types import (
    Exercise,
    ExerciseResponse,
    ExerciseTemplate,
    Set,
    Workout,
    WorkoutResponse,
)
from fitness_tracker.database.models.hevy_app import (
    HevyAppActivatedMuscle,
    HevyAppExercise,
    HevyAppSets,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.repository.hevy_app import (
    HevyAppActivatedMuscleRepository,
    HevyAppExerciseRepository,
    HevyAppSetsRepository,
    HevyAppWorkoutItemRepository,
    HevyAppWorkoutRepository,
)
from fitness_tracker.database.services.base import BaseService


class HevyAppService(BaseService):
    """Hevy App database service class"""

    def __init__(self, engine: Engine) -> None:
        """Initiate the Hevy App service with the engine"""
        super().__init__(engine)
        self.api = HevyAppClient()

    def add_exercises(self, exercises: ExerciseResponse):
        """Add a list of exercises"""
        with self.get_session() as session:
            for exercise in exercises.exercise_templates:
                self.add_exercise(session=session, exercise=exercise)
            session.commit()

    def add_exercise(self, session: Session, exercise: ExerciseTemplate):
        """Add a new exercise"""
        exercise_repo = HevyAppExerciseRepository(session=session)
        instance = HevyAppExercise(
            id=exercise.id,
            name=exercise.title,
            type=exercise.type,
            equipment=exercise.equipment,
            default=True if exercise.is_custom == False else False,
        )
        exercise_repo.merge(instance)
        self.add_primary_activated_muscles(
            session=session, exercise_id=exercise.id, muscle=exercise.primary_muscle_group
        )
        self.add_secondary_activated_muscles(
            session=session, exercise_id=exercise.id, muscles=exercise.secondary_muscle_groups
        )

    def add_primary_activated_muscles(self, session: Session, exercise_id: str, muscle: str):
        """Add primary activated muscles"""
        repo = HevyAppActivatedMuscleRepository(session=session)
        instance = repo.get(exercise_id=exercise_id, muscle=muscle, category="primary_muscle")
        if not instance:
            repo.merge(
                HevyAppActivatedMuscle(
                    exercise_id=exercise_id, muscle=muscle, category="primary_muscle"
                )
            )

    def add_secondary_activated_muscles(
        self, session: Session, exercise_id: str, muscles: list[str]
    ):
        """Add secondary activated muscles"""
        repo = HevyAppActivatedMuscleRepository(session=session)
        for muscle in muscles:
            instance = repo.get(exercise_id=exercise_id, muscle=muscle, category="secondary_muscle")
            if not instance:
                repo.add(
                    HevyAppActivatedMuscle(
                        exercise_id=exercise_id, muscle=muscle, category="secondary_muscle"
                    )
                )

    def add_set(self, session: Session, workout_item_id: int, set: Set):
        """Add sets"""
        repo = HevyAppSetsRepository(session=session)

        entry = HevyAppSets(
            workout_item_id=workout_item_id,
            index=set.index,
            type=set.type,
            weight_kg=set.weight_kg,
            reps=set.reps,
            distance_meters=set.distance_meters,
            duration_seconds=set.duration_seconds,
            rpe=set.rpe,
        )
        if instance := repo.get(workout_item_id=workout_item_id, index=set.index):
            # update the instance
            entry.id = instance.id
            repo.merge(entry)
            return

        repo.insert_ignore(entry)

    def add_workout_item(self, session: Session, workout_id: str, exercise: Exercise):
        """Add workout items"""
        workout_item_repo = HevyAppWorkoutItemRepository(session=session)
        exercise_repo = HevyAppExerciseRepository(session=session)
        # check if the exercise exists
        exercise_instance = exercise_repo.get(id=exercise.exercise_template_id)
        if not exercise_instance:
            # call the API to get the exercise
            exercise_template = self.api.exercises.get_template(exercise.exercise_template_id)
            if exercise_template:
                self.add_exercise(session=session, exercise=exercise_template)
            else:
                raise Exception(f"Exercise with id {exercise.exercise_template_id} does not exist")

        entry = HevyAppWorkoutItem(
            workout_id=workout_id,
            index=exercise.index,
            name=exercise.title,
            notes=exercise.notes,
            superset_id=exercise.superset_id,
            exercise_id=exercise.exercise_template_id,
        )
        if instance := workout_item_repo.get(workout_id=workout_id, index=exercise.index):
            # update the instance
            entry.id = instance.id
            workout_item_repo.merge(entry)
            return

        workout_item_repo.merge(entry)
        session.commit()

        # get the workout item id
        instance = workout_item_repo.get(workout_id=workout_id, index=exercise.index)

        if not instance:
            raise Exception(f"Workout item with index {exercise.index} does not exist")

        for set in exercise.sets:
            self.add_set(session=session, workout_item_id=instance.id, set=set)

    def add_workout(self, session: Session, workout: Workout):
        """Add a new workout"""
        workout_repo = HevyAppWorkoutRepository(session=session)
        instance = HevyAppWorkout(
            id=workout.id,
            title=workout.title,
            description=workout.description,
            start_time=parse(workout.start_time),
            end_time=parse(workout.end_time),
            updated_at=parse(workout.updated_at),
            created_at=parse(workout.created_at),
        )
        workout_repo.merge(instance)

        for exercise in workout.exercises:
            self.add_workout_item(session=session, workout_id=workout.id, exercise=exercise)

    def add_workouts(self, workouts: WorkoutResponse):
        """Add a list of workouts."""
        with self.get_session() as session:
            for workout in workouts.workouts:
                self.add_workout(session=session, workout=workout)
            session.commit()

    def get_workout(self, session: Session, **kwargs: Any):
        """Get a workout by kwargs.

        Args:
            session (Session): The session to use
            kwargs (Any): The kwargs to filter the workout

        """
        workout_repo = HevyAppWorkoutRepository(session=session)
        return workout_repo.get(**kwargs)

    def get_placeholders(self) -> list[HevyAppExercise]:
        """Get placeholders."""
        with self.get_session() as session:
            exercise_repo = HevyAppExerciseRepository(session=session)
            return exercise_repo.get_all(name="#####PLACEHOLDER#####")

    def delete_workout(self, session: Session, **kwargs: Any):
        """Delete a workout by id."""
        workout_repo = HevyAppWorkoutRepository(session=session)
        workout_repo.delete_all(**kwargs)
