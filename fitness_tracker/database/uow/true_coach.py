"""True Coach domain operations for UnitOfWork."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from fitness_tracker.apis.true_coach.types import (
    Assessment,
    AssessmentItem,
    AssessmentResponse,
    Exercise as TCExercise,
    ExerciseResponse as TCExerciseResponse,
    ExerciseTags,
    PutWorkoutItemRequest,
    Workout as TCWorkout,
    WorkoutItem as TCWorkoutItem,
)
from fitness_tracker.database.models.tracker import (
    Sets as TrackerSets,
    WorkoutItem as TrackerWorkoutItem,
)
from fitness_tracker.database.models.true_coach import (
    TrueCoachAssessment,
    TrueCoachAssessmentItem,
    TrueCoachExercise,
    TrueCoachExerciseTags,
    TrueCoachTag,
    TrueCoachWorkout,
    TrueCoachWorkoutItem,
)
from fitness_tracker.database.uow.base import CrudMixin


def _parse_utc_date(s: str) -> datetime:
    """Parse a date string as midnight UTC.

    Args:
        s (str): Date string in ``YYYY-MM-DD`` form.

    Returns:
        datetime: Timezone-aware datetime at 00:00 UTC.
    """
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)


def _parse_utc_iso_micros_z(s: str) -> datetime:
    """Parse an ISO-8601 timestamp ending in Z with microseconds.

    Args:
        s (str): Timestamp string ending in ``Z`` with fractional seconds.

    Returns:
        datetime: Timezone-aware datetime in UTC.
    """
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


class TrueCoachMixin(CrudMixin):
    """True Coach persistence helpers mixed into UnitOfWork."""

    def tc_add_exercises(self, exercises: TCExerciseResponse) -> None:
        """Persist exercises from an API response.

        Args:
            exercises (TCExerciseResponse): Response payload containing exercises.
        """
        for exercise in exercises.exercises:
            self.tc_add_exercise(exercise=exercise)

    def tc_add_exercise(self, exercise: TCExercise) -> None:
        """Insert or update one exercise and its tags.

        Args:
            exercise (TCExercise): Exercise data from the API.
        """
        instance = TrueCoachExercise(
            id=exercise.id,
            name=exercise.exercise_name,
            description=exercise.description,
            url=exercise.url,
            default=exercise.default,
        )
        self.merge(instance)
        self.tc_add_exercise_tags(exercise_id=exercise.id, tag=exercise.tags)

    def tc_add_exercise_tags(self, exercise_id: int, tag: ExerciseTags) -> None:
        """Persist all tag dimensions for an exercise.

        Args:
            exercise_id (int): True Coach exercise id.
            tag (ExerciseTags): Structured tag lists from the API.
        """
        self._tc_ensure_tags(exercise_id, tag.pattern, "pattern")
        self._tc_ensure_tags(exercise_id, tag.plane, "plane")
        if tag.level:
            self._tc_ensure_tags(exercise_id, tag.level, "level")
        if tag.type:
            self._tc_ensure_tags(exercise_id, tag.type, "type")
        if tag.primary_muscles:
            self._tc_ensure_tags(exercise_id, tag.primary_muscles, "primary_muscle")
        if tag.secondary_muscles:
            self._tc_ensure_tags(exercise_id, tag.secondary_muscles, "secondary_muscle")

    def _tc_ensure_tags(
        self,
        exercise_id: int,
        tags: list[str],
        category: str,
    ) -> None:
        """Create-or-get tags and link them to an exercise.

        Replaces the six identical ``add_*_tags`` methods from TrueCoachService.

        Args:
            exercise_id (int): True Coach exercise id.
            tags (list[str]): Tag names to ensure.
            category (str): Tag category (pattern, plane, level, type, etc.).

        Raises:
            RuntimeError: If the tag row cannot be loaded after insert.
        """
        for tag_name in tags:
            instance = self.get(TrueCoachTag, name=tag_name, category=category)
            if not instance:
                self.add(TrueCoachTag(name=tag_name, category=category))
                self.flush()
                instance = self.get(TrueCoachTag, name=tag_name, category=category)
            if instance is None:
                msg = f"Failed to load {category} tag {tag_name!r} after insert"
                raise RuntimeError(msg)
            self.insert_ignore(TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id))

    def tc_add_workout_item(self, workout_item: TCWorkoutItem) -> None:
        """Insert or merge a workout item row.

        Args:
            workout_item (TCWorkoutItem): Workout item from the API.
        """
        instance = TrueCoachWorkoutItem(
            id=workout_item.id,
            workout_id=workout_item.workout_id,
            name=workout_item.name,
            info=workout_item.info,
            comment=workout_item.result,
            is_circuit=workout_item.is_circuit,
            state=workout_item.state,
            position=workout_item.position,
            exercise_id=workout_item.exercise_id,
            assessment_id=workout_item.assessment_id,
        )
        self.merge(instance)

    def tc_update_workout_item(self, workout_item: PutWorkoutItemRequest) -> None:
        """Insert or merge a workout item from a PUT payload.

        Args:
            workout_item (PutWorkoutItemRequest): Updated workout item fields.
        """
        instance = TrueCoachWorkoutItem(
            id=workout_item.id,
            workout_id=workout_item.workout_id,
            name=workout_item.name,
            info=workout_item.info,
            comment=workout_item.result,
            is_circuit=workout_item.is_circuit,
            state=workout_item.state,
            position=workout_item.position,
            exercise_id=workout_item.exercise_id,
            assessment_id=workout_item.assessment_id,
        )
        self.merge(instance)

    def tc_add_workout(self, workout: TCWorkout) -> None:
        """Insert or merge a workout and prune removed items.

        Args:
            workout (TCWorkout): Workout payload from the API.
        """
        if workout.workout_item_ids:
            self.tc_remove_old_workout_items(
                workout_id=workout.id,
                workout_items=workout.workout_item_ids,
            )

        instance = TrueCoachWorkout(
            id=workout.id,
            title=workout.title,
            due=_parse_utc_date(workout.due),
            short_description=workout.short_description,
            state=workout.state,
            rest_day=workout.rest_day,
            created_at=_parse_utc_iso_micros_z(workout.created_at),
            updated_at=_parse_utc_iso_micros_z(workout.updated_at),
        )
        self.merge(instance)

    def tc_remove_old_workout_items(
        self,
        workout_id: int,
        workout_items: list[int],
    ) -> None:
        """Delete workout items (and related rows) not present in the keep list.

        Args:
            workout_id (int): Parent workout id.
            workout_items (list[int]): Item ids to retain.
        """
        items_to_keep = workout_items if workout_items else [-1]

        tc_subq = (
            self._session.query(TrueCoachWorkoutItem.id)
            .filter(
                TrueCoachWorkoutItem.workout_id == workout_id,
                ~TrueCoachWorkoutItem.id.in_(items_to_keep),
            )
            .subquery()
        )

        wi_subq = (
            self._session.query(TrackerWorkoutItem.id)
            .filter(TrackerWorkoutItem.true_coach_id.in_(select(tc_subq.c.id)))
            .subquery()
        )

        self._session.query(TrackerSets).filter(
            TrackerSets.workout_item_id.in_(select(wi_subq.c.id))
        ).delete(synchronize_session=False)

        self._session.query(TrackerWorkoutItem).filter(
            TrackerWorkoutItem.id.in_(select(wi_subq.c.id))
        ).delete(synchronize_session=False)

        self._session.query(TrueCoachWorkoutItem).filter(
            TrueCoachWorkoutItem.id.in_(select(tc_subq.c.id))
        ).delete(synchronize_session=False)

        self.flush()

    def tc_get_workout(self, **kwargs: Any) -> TrueCoachWorkout | None:
        """Load a single True Coach workout by filters.

        Args:
            **kwargs (Any): Equality filters.

        Returns:
            TrueCoachWorkout | None: The workout row if found.
        """
        return self.get(TrueCoachWorkout, **kwargs)

    def tc_get_workouts(self, **kwargs: Any) -> list[TrueCoachWorkout]:
        """Load True Coach workouts matching the given filters.

        Args:
            **kwargs (Any): Equality filters.

        Returns:
            list[TrueCoachWorkout]: All matching workout rows.
        """
        return self.get_all(TrueCoachWorkout, **kwargs)

    def tc_get_workout_item(self, **kwargs: Any) -> TrueCoachWorkoutItem | None:
        """Load a single True Coach workout item by filters.

        Args:
            **kwargs (Any): Equality filters.

        Returns:
            TrueCoachWorkoutItem | None: The workout item row if found.
        """
        return self.get(TrueCoachWorkoutItem, **kwargs)

    def tc_get_workout_items(self, **kwargs: Any) -> list[TrueCoachWorkoutItem]:
        """Load True Coach workout items matching the given filters.

        Args:
            **kwargs (Any): Equality filters.

        Returns:
            list[TrueCoachWorkoutItem]: All matching workout item rows.
        """
        return self.get_all(TrueCoachWorkoutItem, **kwargs)

    def tc_add_assessment_item(self, assessment: AssessmentItem) -> None:
        """Insert or merge one assessment item row.

        Args:
            assessment (AssessmentItem): Assessment item from the API.
        """
        instance = TrueCoachAssessmentItem(
            id=assessment.id,
            assessment_id=assessment.assessment_id,
            value=assessment.value,
            note=assessment.note,
            created_at=_parse_utc_iso_micros_z(assessment.created_at),
            updated_at=_parse_utc_iso_micros_z(assessment.updated_at),
            date=_parse_utc_iso_micros_z(assessment.date),
            completed_date=_parse_utc_date(assessment.completed_date),
        )
        self.merge(instance)

    def _tc_add_assessment(self, assessment: Assessment) -> None:
        """Insert or merge the parent assessment row.

        Args:
            assessment (Assessment): Assessment metadata from the API.
        """
        instance = TrueCoachAssessment(
            id=assessment.id,
            assessment_group_id=assessment.assessment_group_id,
            name=assessment.name,
            units=assessment.units,
            order=assessment.order,
            target=assessment.target,
            target_percentage=assessment.target_percentage,
            linked_assessment_id=assessment.linked_assessment_id,
            created_at=_parse_utc_iso_micros_z(assessment.created_at),
            updated_at=_parse_utc_iso_micros_z(assessment.updated_at),
        )
        self.merge(instance)

    def tc_add_assessment(self, assessment: AssessmentResponse) -> None:
        """Persist an assessment and its item rows from an API response.

        Args:
            assessment (AssessmentResponse): Response payload with assessment and items.
        """
        self._tc_add_assessment(assessment=assessment.assessment)
        for assessment_item in assessment.assessment_items:
            self.tc_add_assessment_item(assessment=assessment_item)

    def tc_delete_workout(self, workout: TrueCoachWorkout) -> None:
        """Remove a True Coach workout row.

        Args:
            workout (TrueCoachWorkout): ORM instance to delete.
        """
        self.delete(workout)
