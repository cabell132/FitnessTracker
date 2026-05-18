"""Hevy App domain operations for UnitOfWork."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, cast

from dateutil.parser import parse

from fitness_tracker.apis.hevy_app.types import (
    Exercise as HevyExercisePayload,
    ExerciseResponse as HevyExerciseResponse,
    ExerciseTemplate,
    Set as HevySet,
    Workout as HevyWorkout,
    WorkoutResponse as HevyWorkoutResponse,
)
from fitness_tracker.database.models.hevy_app import (
    HevyAppActivatedMuscle,
    HevyAppExercise,
    HevyAppSets,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.uow.base import CrudMixin
from fitness_tracker.database.uow.errors import HevyAppPersistenceError


class HevyExerciseTemplateSource(Protocol):
    """Source capable of loading a Hevy exercise template by id."""

    def get_template(self, template_id: str) -> ExerciseTemplate | None:
        """Return an exercise template for ``template_id`` when available.

        Args:
            template_id (str): Hevy exercise template id.

        Returns:
            ExerciseTemplate | None: Template when available.
        """
        ...


class HevyMixin(CrudMixin):
    """Hevy App persistence helpers mixed into UnitOfWork."""

    def hevy_add_exercises(self, exercises: HevyExerciseResponse) -> None:
        """Persist all exercise templates from a paginated API response.

        Args:
            exercises (HevyExerciseResponse): API payload with exercise templates.
        """
        for exercise in exercises.exercise_templates:
            self.hevy_add_exercise(exercise=exercise)

    def hevy_add_exercise(self, exercise: ExerciseTemplate) -> None:
        """Insert or merge one exercise template and its muscle links.

        Args:
            exercise (ExerciseTemplate): Exercise metadata from the API.
        """
        instance = HevyAppExercise(
            id=exercise.id,
            name=exercise.title,
            type=exercise.type,
            equipment=exercise.equipment,
            default=not exercise.is_custom,
        )
        self.merge(instance)
        self._hevy_add_primary_muscle(
            exercise_id=exercise.id,
            muscle=exercise.primary_muscle_group,
        )
        self._hevy_add_secondary_muscles(
            exercise_id=exercise.id,
            muscles=exercise.secondary_muscle_groups,
        )

    def _hevy_add_primary_muscle(self, exercise_id: str, muscle: str) -> None:
        """Persist the primary muscle group for an exercise if missing.

        Args:
            exercise_id (str): Hevy exercise template id.
            muscle (str): Primary muscle group name.
        """
        existing = self.get(
            HevyAppActivatedMuscle,
            exercise_id=exercise_id,
            muscle=muscle,
            category="primary_muscle",
        )
        if not existing:
            self.merge(
                HevyAppActivatedMuscle(
                    exercise_id=exercise_id,
                    muscle=muscle,
                    category="primary_muscle",
                )
            )

    def _hevy_add_secondary_muscles(
        self,
        exercise_id: str,
        muscles: Sequence[str],
    ) -> None:
        """Persist secondary muscle groups for an exercise.

        Args:
            exercise_id (str): Hevy exercise template id.
            muscles (Sequence[str]): Secondary muscle group names.
        """
        for muscle in muscles:
            existing = self.get(
                HevyAppActivatedMuscle,
                exercise_id=exercise_id,
                muscle=muscle,
                category="secondary_muscle",
            )
            if not existing:
                self.add(
                    HevyAppActivatedMuscle(
                        exercise_id=exercise_id,
                        muscle=muscle,
                        category="secondary_muscle",
                    )
                )

    def hevy_add_set(self, workout_item_id: int, workout_set: HevySet) -> None:
        """Insert or update one set row for a workout item.

        Args:
            workout_item_id (int): Database id of the parent workout item.
            workout_set (HevySet): Set payload from the API.
        """
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
        if instance := self.get(
            HevyAppSets,
            workout_item_id=workout_item_id,
            index=workout_set.index,
        ):
            entry.id = instance.id
            self.merge(entry)
            return

        self.insert_ignore(entry)

    def hevy_add_workout_item(
        self,
        workout_id: str,
        exercise: HevyExercisePayload,
        *,
        exercise_template_source: HevyExerciseTemplateSource | None = None,
    ) -> None:
        """Insert or merge a workout item and its sets.

        Args:
            workout_id (str): Hevy workout id.
            exercise (HevyExercisePayload): Exercise block from the API.
            exercise_template_source (HevyExerciseTemplateSource | None): Optional
                source for loading missing exercise templates.

        Raises:
            HevyAppPersistenceError: If the item row is missing after merge.
        """
        self._hevy_ensure_exercise_template(
            exercise,
            exercise_template_source=exercise_template_source,
        )

        entry = HevyAppWorkoutItem(
            workout_id=workout_id,
            index=exercise.index,
            name=exercise.title,
            notes=exercise.notes or "",
            superset_id=exercise.superset_id or None,
            exercise_id=exercise.exercise_template_id,
        )
        if instance := self.get(
            HevyAppWorkoutItem,
            workout_id=workout_id,
            index=exercise.index,
        ):
            entry.id = instance.id
            self.merge(entry)
            return

        self.merge(entry)
        self.flush()

        instance = self.get(
            HevyAppWorkoutItem,
            workout_id=workout_id,
            index=exercise.index,
        )
        if not instance:
            msg = f"Workout item with index {exercise.index} does not exist"
            raise HevyAppPersistenceError(msg)

        wid = cast(int, instance.id)
        for ws in exercise.sets:
            self.hevy_add_set(workout_item_id=wid, workout_set=ws)

    def hevy_add_workout(
        self,
        workout: HevyWorkout,
        *,
        exercise_template_source: HevyExerciseTemplateSource | None = None,
    ) -> None:
        """Insert or merge a workout and nested items.

        Args:
            workout (HevyWorkout): Workout payload from the API.
            exercise_template_source (HevyExerciseTemplateSource | None): Optional
                source for loading missing exercise templates.
        """
        instance = HevyAppWorkout(
            id=workout.id,
            title=workout.title,
            description=workout.description or "",
            start_time=parse(workout.start_time),
            end_time=parse(workout.end_time),
            updated_at=parse(workout.updated_at),
            created_at=parse(workout.created_at),
        )
        self.merge(instance)

        for exercise in workout.exercises:
            self.hevy_add_workout_item(
                workout_id=workout.id,
                exercise=exercise,
                exercise_template_source=exercise_template_source,
            )

    def hevy_add_workouts(
        self,
        workouts: HevyWorkoutResponse,
        *,
        exercise_template_source: HevyExerciseTemplateSource | None = None,
    ) -> None:
        """Persist all workouts from a list response.

        Args:
            workouts (HevyWorkoutResponse): API payload containing workouts.
            exercise_template_source (HevyExerciseTemplateSource | None): Optional
                source for loading missing exercise templates.
        """
        for workout in workouts.workouts:
            self.hevy_add_workout(
                workout=workout,
                exercise_template_source=exercise_template_source,
            )

    def hevy_get_workout(self, **kwargs: Any) -> HevyAppWorkout | None:
        """Load one Hevy workout row by filter.

        Args:
            **kwargs (Any): Equality filters.

        Returns:
            HevyAppWorkout | None: Matching row when present.
        """
        return self.get(HevyAppWorkout, **kwargs)

    def hevy_get_placeholders(self) -> list[HevyAppExercise]:
        """Return exercises marked as placeholders.

        Returns:
            list[HevyAppExercise]: Rows whose name is the placeholder sentinel.
        """
        return self.get_all(HevyAppExercise, name="#####PLACEHOLDER#####")

    def hevy_delete_workout(self, **kwargs: Any) -> None:
        """Delete Hevy workouts matching the given filters.

        Args:
            **kwargs (Any): Equality filters.
        """
        self.delete_all(HevyAppWorkout, **kwargs)

    def _hevy_ensure_exercise_template(
        self,
        exercise: HevyExercisePayload,
        *,
        exercise_template_source: HevyExerciseTemplateSource | None = None,
    ) -> None:
        """Load an exercise template from the API when missing locally.

        Args:
            exercise (HevyExercisePayload): Workout block referring to a template.
            exercise_template_source (HevyExerciseTemplateSource | None): Optional
                source for loading missing exercise templates.

        Raises:
            HevyAppPersistenceError: If the template cannot be fetched.
        """
        if self.get(HevyAppExercise, id=exercise.exercise_template_id):
            return
        if exercise_template_source is None:
            msg = (
                f"Exercise with id {exercise.exercise_template_id} is missing locally "
                "and no Hevy template source was provided"
            )
            raise HevyAppPersistenceError(msg)
        template = exercise_template_source.get_template(exercise.exercise_template_id)
        if template:
            self.hevy_add_exercise(exercise=template)
            return
        msg = f"Exercise with id {exercise.exercise_template_id} does not exist"
        raise HevyAppPersistenceError(msg)
