"""Database service for persisting Hevy App API data."""

from collections.abc import Sequence
from typing import Any, cast

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


class HevyAppPersistenceError(Exception):
    """Raised when Hevy workout or exercise data is missing or inconsistent."""


class HevyAppService(BaseService):
    """Persists Hevy App workouts, exercises, and sets via repositories."""

    def __init__(self, engine: Engine) -> None:
        """Create the service with a SQLAlchemy engine.

        Args:
            engine (Engine): SQLAlchemy engine used for sessions.
        """
        super().__init__(engine)
        self.api = HevyAppClient()

    def add_exercises(self, exercises: ExerciseResponse) -> None:
        """Persist all exercise templates from a paginated API response.

        Args:
            exercises (ExerciseResponse): API payload containing exercise templates.

        Returns:
            None: Not used; persists inside a managed session.
        """
        with self.get_session() as session:
            for exercise in exercises.exercise_templates:
                self.add_exercise(session=session, exercise=exercise)
            session.commit()

    def add_exercise(self, session: Session, exercise: ExerciseTemplate) -> None:
        """Insert or merge one exercise template and its muscle links.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise (ExerciseTemplate): Exercise metadata from the API.

        Returns:
            None: Not used; writes through the given session.
        """
        exercise_repo = HevyAppExerciseRepository(session=session)
        instance = HevyAppExercise(
            id=exercise.id,
            name=exercise.title,
            type=exercise.type,
            equipment=exercise.equipment,
            default=not exercise.is_custom,
        )
        exercise_repo.merge(instance)
        self.add_primary_activated_muscles(
            session=session, exercise_id=exercise.id, muscle=exercise.primary_muscle_group
        )
        self.add_secondary_activated_muscles(
            session=session, exercise_id=exercise.id, muscles=exercise.secondary_muscle_groups
        )

    def add_primary_activated_muscles(
        self, session: Session, exercise_id: str, muscle: str
    ) -> None:
        """Persist the primary muscle group for an exercise if missing.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise_id (str): Hevy exercise template id.
            muscle (str): Primary muscle group name.

        Returns:
            None: Not used; writes through the given session.
        """
        repo = HevyAppActivatedMuscleRepository(session=session)
        instance = repo.get(exercise_id=exercise_id, muscle=muscle, category="primary_muscle")
        if not instance:
            repo.merge(
                HevyAppActivatedMuscle(
                    exercise_id=exercise_id, muscle=muscle, category="primary_muscle"
                )
            )

    def add_secondary_activated_muscles(
        self, session: Session, exercise_id: str, muscles: Sequence[str]
    ) -> None:
        """Persist secondary muscle groups for an exercise.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise_id (str): Hevy exercise template id.
            muscles (Sequence[str]): Secondary muscle group names.

        Returns:
            None: Not used; writes through the given session.
        """
        repo = HevyAppActivatedMuscleRepository(session=session)
        for muscle in muscles:
            instance = repo.get(exercise_id=exercise_id, muscle=muscle, category="secondary_muscle")
            if not instance:
                repo.add(
                    HevyAppActivatedMuscle(
                        exercise_id=exercise_id, muscle=muscle, category="secondary_muscle"
                    )
                )

    def add_set(self, session: Session, workout_item_id: int, workout_set: Set) -> None:
        """Insert or update one set row for a workout item.

        Args:
            session (Session): Active SQLAlchemy session.
            workout_item_id (int): Database id of the parent workout item.
            workout_set (Set): Set payload from the API.

        Returns:
            None: Not used; writes through the given session.
        """
        repo = HevyAppSetsRepository(session=session)

        entry = HevyAppSets(
            workout_item_id=workout_item_id,
            index=workout_set.index,
            type=workout_set.type,
            weight_kg=workout_set.weight_kg,
            reps=workout_set.reps,
            distance_meters=workout_set.distance_meters,
            duration_seconds=workout_set.duration_seconds,
            rpe=workout_set.rpe,
        )
        if instance := repo.get(workout_item_id=workout_item_id, index=workout_set.index):
            entry.id = instance.id
            repo.merge(entry)
            return

        repo.insert_ignore(entry)

    def add_workout_item(self, session: Session, workout_id: str, exercise: Exercise) -> None:
        """Insert or merge a workout item and its sets.

        Args:
            session (Session): Active SQLAlchemy session.
            workout_id (str): Hevy workout id.
            exercise (Exercise): Exercise block from the API.

        Returns:
            None: Not used; writes through the given session.

        Raises:
            HevyAppPersistenceError: If the exercise template cannot be loaded or the item row
                is missing after merge.
        """
        workout_item_repo = HevyAppWorkoutItemRepository(session=session)
        self._ensure_exercise_template(session, exercise)

        entry = HevyAppWorkoutItem(
            workout_id=workout_id,
            index=exercise.index,
            name=exercise.title,
            notes=exercise.notes,
            superset_id=exercise.superset_id,
            exercise_id=exercise.exercise_template_id,
        )
        if instance := workout_item_repo.get(workout_id=workout_id, index=exercise.index):
            entry.id = instance.id
            workout_item_repo.merge(entry)
            return

        workout_item_repo.merge(entry)
        session.commit()

        instance = workout_item_repo.get(workout_id=workout_id, index=exercise.index)

        if not instance:
            msg = f"Workout item with index {exercise.index} does not exist"
            raise HevyAppPersistenceError(msg)

        wid = cast(int, instance.id)
        for ws in exercise.sets:
            self.add_set(session=session, workout_item_id=wid, workout_set=ws)

    def add_workout(self, session: Session, workout: Workout) -> None:
        """Insert or merge a workout and nested items.

        Args:
            session (Session): Active SQLAlchemy session.
            workout (Workout): Workout payload from the API.

        Returns:
            None: Not used; writes through the given session.
        """
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

    def add_workouts(self, workouts: WorkoutResponse) -> None:
        """Persist all workouts from a list response.

        Args:
            workouts (WorkoutResponse): API payload containing workouts.

        Returns:
            None: Not used; persists inside a managed session.
        """
        with self.get_session() as session:
            for workout in workouts.workouts:
                self.add_workout(session=session, workout=workout)
            session.commit()

    def get_workout(self, session: Session, **kwargs: Any) -> HevyAppWorkout | None:
        """Load one workout row using repository filters.

        Args:
            session (Session): Active SQLAlchemy session.
            **kwargs (Any): Filters passed to ``HevyAppWorkoutRepository.get``.

        Returns:
            HevyAppWorkout | None: Matching row when present.
        """
        workout_repo = HevyAppWorkoutRepository(session=session)
        return workout_repo.get(**kwargs)

    def get_placeholders(self) -> list[HevyAppExercise]:
        """Return exercises marked as placeholders.

        Returns:
            list[HevyAppExercise]: Rows whose name is the placeholder sentinel.
        """
        with self.get_session() as session:
            exercise_repo = HevyAppExerciseRepository(session=session)
            return exercise_repo.get_all(name="#####PLACEHOLDER#####")

    def delete_workout(self, session: Session, **kwargs: Any) -> None:
        """Delete workouts matching the given filters.

        Args:
            session (Session): Active SQLAlchemy session.
            **kwargs (Any): Filters passed to ``HevyAppWorkoutRepository.delete_all``.

        Returns:
            None: Not used; deletes via the given session.
        """
        workout_repo = HevyAppWorkoutRepository(session=session)
        workout_repo.delete_all(**kwargs)

    def _ensure_exercise_template(self, session: Session, exercise: Exercise) -> None:
        """Load an exercise template from the API when it is missing locally.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise (Exercise): Workout block referring to a template id.

        Returns:
            None: Not used; may insert rows through the session.

        Raises:
            HevyAppPersistenceError: If the template cannot be fetched from the API.
        """
        exercise_repo = HevyAppExerciseRepository(session=session)
        if exercise_repo.get(id=exercise.exercise_template_id):
            return
        exercise_template = self.api.exercises.get_template(exercise.exercise_template_id)
        if exercise_template:
            self.add_exercise(session=session, exercise=exercise_template)
            return
        msg = f"Exercise with id {exercise.exercise_template_id} does not exist"
        raise HevyAppPersistenceError(msg)
