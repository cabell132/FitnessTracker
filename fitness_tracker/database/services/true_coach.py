"""Database service for persisting True Coach API data."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from fitness_tracker.apis.true_coach.types import (
    Assessment,
    AssessmentItem,
    AssessmentResponse,
    Exercise,
    ExerciseResponse,
    ExerciseTags,
    PutWorkoutItemRequest,
    Workout,
    WorkoutItem,
)
from fitness_tracker.database.models.tracker import (
    Sets as SetsTrackerModel,
)
from fitness_tracker.database.models.tracker import (
    WorkoutItem as WorkoutItemTrackerModel,
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
from fitness_tracker.database.repository.true_coach import (
    TrueCoachAssessmentItemRepository,
    TrueCoachAssessmentRepository,
    TrueCoachExerciseRepository,
    TrueCoachExerciseTagsRepository,
    TrueCoachTagRepository,
    TrueCoachWorkoutItemRepository,
    TrueCoachWorkoutRepository,
)
from fitness_tracker.database.services.base import BaseService


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


class TrueCoachService(BaseService):
    """True Coach database service class."""

    def __init__(self, engine: Engine) -> None:
        """Create the service.

        Args:
            engine (Engine): SQLAlchemy engine used for sessions.
        """
        super().__init__(engine)

    def add_exercises(self, exercises: ExerciseResponse) -> None:
        """Persist exercises from an API response.

        Args:
            exercises (ExerciseResponse): Response payload containing exercises to store.
        """
        with self.get_session() as session:
            for exercise in exercises.exercises:
                self.add_exercise(session=session, exercise=exercise)
            session.commit()

    def add_exercise(self, session: Session, exercise: Exercise) -> None:
        """Insert or update one exercise and its tags.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise (Exercise): Exercise data from the API.
        """
        exercise_repo = TrueCoachExerciseRepository(session=session)
        instance = TrueCoachExercise(
            id=exercise.id,
            name=exercise.exercise_name,
            description=exercise.description,
            url=exercise.url,
            default=exercise.default,
        )
        exercise_repo.merge(instance)
        self.add_exercise_tag(session=session, exercise_id=exercise.id, tag=exercise.tags)

    def add_exercise_tag(self, session: Session, exercise_id: int, tag: ExerciseTags) -> None:
        """Persist all tag dimensions for an exercise.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise_id (int): True Coach exercise id.
            tag (ExerciseTags): Structured tag lists from the API.
        """
        self.add_pattern_tags(session=session, exercise_id=exercise_id, tags=tag.pattern)
        self.add_plane_tags(session=session, exercise_id=exercise_id, tags=tag.plane)
        if tag.level:
            self.add_level_tags(session=session, exercise_id=exercise_id, tags=tag.level)
        if tag.type:
            self.add_type_tags(session=session, exercise_id=exercise_id, tags=tag.type)
        if tag.primary_muscles:
            self.add_primary_muscle_tags(
                session=session, exercise_id=exercise_id, tags=tag.primary_muscles
            )
        if tag.secondary_muscles:
            self.add_secondary_muscle_tags(
                session=session, exercise_id=exercise_id, tags=tag.secondary_muscles
            )

    def add_pattern_tags(self, session: Session, exercise_id: int, tags: list[str]) -> None:
        """Link pattern tags to an exercise, creating tags when missing.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise_id (int): True Coach exercise id.
            tags (list[str]): Pattern tag names.

        Raises:
            RuntimeError: If the tag row cannot be loaded after insert.
        """
        tag_repo = TrueCoachTagRepository(session=session)
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="pattern")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="pattern"))
                session.commit()
                instance = tag_repo.get(name=tag, category="pattern")
            if instance is None:
                msg = f"Failed to load pattern tag {tag!r} after insert"
                raise RuntimeError(msg)
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_plane_tags(self, session: Session, exercise_id: int, tags: list[str]) -> None:
        """Link plane tags to an exercise, creating tags when missing.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise_id (int): True Coach exercise id.
            tags (list[str]): Plane tag names.

        Raises:
            RuntimeError: If the tag row cannot be loaded after insert.
        """
        tag_repo = TrueCoachTagRepository(session=session)
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="plane")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="plane"))
                session.commit()
                instance = tag_repo.get(name=tag, category="plane")
            if instance is None:
                msg = f"Failed to load plane tag {tag!r} after insert"
                raise RuntimeError(msg)
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_level_tags(self, session: Session, exercise_id: int, tags: list[str]) -> None:
        """Link level tags to an exercise, creating tags when missing.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise_id (int): True Coach exercise id.
            tags (list[str]): Level tag names.

        Raises:
            RuntimeError: If the tag row cannot be loaded after insert.
        """
        tag_repo = TrueCoachTagRepository(session=session)
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="level")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="level"))
                session.commit()
                instance = tag_repo.get(name=tag, category="level")
            if instance is None:
                msg = f"Failed to load level tag {tag!r} after insert"
                raise RuntimeError(msg)
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_type_tags(self, session: Session, exercise_id: int, tags: list[str]) -> None:
        """Link type tags to an exercise, creating tags when missing.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise_id (int): True Coach exercise id.
            tags (list[str]): Type tag names.

        Raises:
            RuntimeError: If the tag row cannot be loaded after insert.
        """
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        tag_repo = TrueCoachTagRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="type")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="type"))
                session.commit()
                instance = tag_repo.get(name=tag, category="type")
            if instance is None:
                msg = f"Failed to load type tag {tag!r} after insert"
                raise RuntimeError(msg)
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_primary_muscle_tags(self, session: Session, exercise_id: int, tags: list[str]) -> None:
        """Link primary-muscle tags to an exercise, creating tags when missing.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise_id (int): True Coach exercise id.
            tags (list[str]): Primary muscle tag names.

        Raises:
            RuntimeError: If the tag row cannot be loaded after insert.
        """
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        tag_repo = TrueCoachTagRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="primary_muscle")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="primary_muscle"))
                session.commit()
                instance = tag_repo.get(name=tag, category="primary_muscle")
            if instance is None:
                msg = f"Failed to load primary muscle tag {tag!r} after insert"
                raise RuntimeError(msg)
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_secondary_muscle_tags(
        self, session: Session, exercise_id: int, tags: list[str]
    ) -> None:
        """Link secondary-muscle tags to an exercise, creating tags when missing.

        Args:
            session (Session): Active SQLAlchemy session.
            exercise_id (int): True Coach exercise id.
            tags (list[str]): Secondary muscle tag names.

        Raises:
            RuntimeError: If the tag row cannot be loaded after insert.
        """
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        tag_repo = TrueCoachTagRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="secondary_muscle")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="secondary_muscle"))
                session.commit()
                instance = tag_repo.get(name=tag, category="secondary_muscle")
            if instance is None:
                msg = f"Failed to load secondary muscle tag {tag!r} after insert"
                raise RuntimeError(msg)
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_workout_item(self, session: Session, workout_item: WorkoutItem) -> None:
        """Insert or merge a workout item row.

        Args:
            session (Session): Active SQLAlchemy session.
            workout_item (WorkoutItem): Workout item from the API.
        """
        workout_item_repo = TrueCoachWorkoutItemRepository(session=session)
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
        workout_item_repo.merge(instance)

    def update_workout_item(self, session: Session, workout_item: PutWorkoutItemRequest) -> None:
        """Insert or merge a workout item from a PUT payload.

        Args:
            session (Session): Active SQLAlchemy session.
            workout_item (PutWorkoutItemRequest): Updated workout item fields from the API.

        Returns:
            None: Not used; writes through the given session.
        """
        workout_item_repo = TrueCoachWorkoutItemRepository(session=session)
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
        workout_item_repo.merge(instance)

    def add_workout(self, session: Session, workout: Workout) -> None:
        """Insert or merge a workout and prune removed items.

        Args:
            session (Session): Active SQLAlchemy session.
            workout (Workout): Workout payload from the API.

        Returns:
            None: Not used; writes through the given session.
        """
        # Remove old workout items
        if workout.workout_item_ids:
            self.remove_old_workout_items(
                session=session, workout_id=workout.id, workout_items=workout.workout_item_ids
            )

        workout_repo = TrueCoachWorkoutRepository(session=session)
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
        workout_repo.merge(instance)

    def remove_old_workout_items(
        self, session: Session, workout_id: int, workout_items: list[int]
    ) -> None:
        """Delete workout items (and related rows) not present in the keep list.

        Args:
            session (Session): Active SQLAlchemy session.
            workout_id (int): Parent workout id.
            workout_items (list[int]): Item ids to retain; if empty, all items for the workout
                are removed.

        Returns:
            None: Not used; deletes and commits on the session.
        """
        # If workout_items is empty, default to a list with a dummy value:
        items_to_keep = workout_items if workout_items else [-1]

        # Build a subquery to fetch TrueCoachWorkoutItem IDs to delete.
        tc_subq = (
            session.query(TrueCoachWorkoutItem.id)
            .filter(
                TrueCoachWorkoutItem.workout_id == workout_id,
                ~TrueCoachWorkoutItem.id.in_(items_to_keep),
            )
            .subquery()
        )

        # Build a subquery to fetch WorkoutItem IDs associated with the TrueCoachWorkoutItem IDs
        wi_subq = (
            session.query(WorkoutItemTrackerModel.id)
            .filter(WorkoutItemTrackerModel.true_coach_id.in_(select(tc_subq.c.id)))
            .subquery()
        )

        # Delete SETS records where workout_item_id is in the list of WorkoutItem IDs.
        session.query(SetsTrackerModel).filter(
            SetsTrackerModel.workout_item_id.in_(select(wi_subq.c.id))
        ).delete(synchronize_session=False)

        # Delete WorkoutItem records.
        session.query(WorkoutItemTrackerModel).filter(
            WorkoutItemTrackerModel.id.in_(select(wi_subq.c.id))
        ).delete(synchronize_session=False)

        # Delete TrueCoachWorkoutItem records.
        session.query(TrueCoachWorkoutItem).filter(
            TrueCoachWorkoutItem.id.in_(select(tc_subq.c.id))
        ).delete(synchronize_session=False)

        # Commit the transaction.
        session.commit()

    def get_workout(self, session: Session, **kwargs: Any) -> TrueCoachWorkout | None:
        """Load a single workout by repository filters.

        Args:
            session (Session): Active SQLAlchemy session.
            **kwargs (Any): Arguments forwarded to ``TrueCoachWorkoutRepository.get``.

        Returns:
            TrueCoachWorkout | None: The workout row if found, otherwise ``None``.
        """
        workout_repo = TrueCoachWorkoutRepository(session=session)
        return workout_repo.get(**kwargs)

    def get_workouts(self, session: Session, **kwargs: Any) -> list[TrueCoachWorkout]:
        """Load workouts matching the given filters.

        Args:
            session (Session): Active SQLAlchemy session.
            **kwargs (Any): Arguments forwarded to ``TrueCoachWorkoutRepository.get_all``.

        Returns:
            list[TrueCoachWorkout]: All matching workout rows (possibly empty).
        """
        workout_repo = TrueCoachWorkoutRepository(session=session)
        return workout_repo.get_all(**kwargs)

    def get_workout_item(self, session: Session, **kwargs: Any) -> TrueCoachWorkoutItem | None:
        """Load a single workout item by repository filters.

        Args:
            session (Session): Active SQLAlchemy session.
            **kwargs (Any): Arguments forwarded to ``TrueCoachWorkoutItemRepository.get``.

        Returns:
            TrueCoachWorkoutItem | None: The workout item row if found, otherwise ``None``.
        """
        workout_item_repo = TrueCoachWorkoutItemRepository(session=session)
        return workout_item_repo.get(**kwargs)

    def get_workout_items(self, session: Session, **kwargs: Any) -> list[TrueCoachWorkoutItem]:
        """Load workout items matching the given filters.

        Args:
            session (Session): Active SQLAlchemy session.
            **kwargs (Any): Arguments forwarded to ``TrueCoachWorkoutItemRepository.get_all``.

        Returns:
            list[TrueCoachWorkoutItem]: All matching workout item rows (possibly empty).
        """
        workout_item_repo = TrueCoachWorkoutItemRepository(session=session)
        return workout_item_repo.get_all(**kwargs)

    def add_assessment_item(self, session: Session, assessment: AssessmentItem) -> None:
        """Insert or merge one assessment item row.

        Args:
            session (Session): Active SQLAlchemy session.
            assessment (AssessmentItem): Assessment item from the API.

        Returns:
            None: Not used; writes through the given session.
        """
        assessment_repo = TrueCoachAssessmentItemRepository(session=session)
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
        assessment_repo.merge(instance)

    def _add_assessment(self, session: Session, assessment: Assessment) -> None:
        """Insert or merge the parent assessment row.

        Args:
            session (Session): Active SQLAlchemy session.
            assessment (Assessment): Assessment metadata from the API.

        Returns:
            None: Not used; writes through the given session.
        """
        assessment_repo = TrueCoachAssessmentRepository(session=session)
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
        assessment_repo.merge(instance)

    def add_assessment(self, assessment: AssessmentResponse) -> None:
        """Persist an assessment and its item rows from an API response.

        Args:
            assessment (AssessmentResponse): Response payload containing assessment and items.

        Returns:
            None: Not used; opens a session and commits.
        """
        with self.get_session() as session:
            self._add_assessment(session=session, assessment=assessment.assessment)
            for assessment_item in assessment.assessment_items:
                self.add_assessment_item(session=session, assessment=assessment_item)
            session.commit()

    def delete_workout(self, session: Session, workout: TrueCoachWorkout) -> None:
        """Remove a workout row and commit.

        Args:
            session (Session): Active SQLAlchemy session.
            workout (TrueCoachWorkout): ORM instance to delete.

        Returns:
            None: Not used; deletes and commits.
        """
        workout_repo = TrueCoachWorkoutRepository(session=session)
        workout_repo.delete(workout)
        session.commit()
