from datetime import datetime
from typing import Any

from sqlalchemy import text
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
from fitness_tracker.database.models.true_coach import (
    TrueCoachAssessment,
    TrueCoachAssessmentItem,
    TrueCoachExercise,
    TrueCoachExerciseTags,
    TrueCoachTag,
    TrueCoachWorkout,
    TrueCoachWorkoutItem,
)
from fitness_tracker.database.models.tracker import (
    Sets as SetsTrackerModel,
    WorkoutItem as WorkoutItemTrackerModel,
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


class TrueCoachService(BaseService):
    """True Coach database service class."""

    def __init__(self, engine: Engine) -> None:
        """Initiate the True Coach service with the engine."""
        super().__init__(engine)

    def add_exercises(self, exercises: ExerciseResponse):
        """Add a list of exercises."""
        with self.get_session() as session:
            for exercise in exercises.exercises:
                self.add_exercise(session=session, exercise=exercise)
            session.commit()

    def add_exercise(self, session: Session, exercise: Exercise):
        """Add a new exercise."""
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

    def add_exercise_tag(self, session: Session, exercise_id: int, tag: ExerciseTags):
        """Add a new exercise tag."""
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

    def add_pattern_tags(self, session: Session, exercise_id: int, tags: list[str]):
        """Add pattern tags."""
        tag_repo = TrueCoachTagRepository(session=session)
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="pattern")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="pattern"))
                session.commit()
                instance = tag_repo.get(name=tag, category="pattern")
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_plane_tags(self, session: Session, exercise_id: int, tags: list[str]):
        """Add plane tags."""
        tag_repo = TrueCoachTagRepository(session=session)
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="plane")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="plane"))
                session.commit()
                instance = tag_repo.get(name=tag, category="plane")
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_level_tags(self, session: Session, exercise_id: int, tags: list[str]):
        """Add level tags."""
        tag_repo = TrueCoachTagRepository(session=session)
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="level")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="level"))
                session.commit()
                instance = tag_repo.get(name=tag, category="level")
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_type_tags(self, session: Session, exercise_id: int, tags: list[str]):
        """Get the tags for a specific type."""
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        tag_repo = TrueCoachTagRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="type")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="type"))
                session.commit()
                instance = tag_repo.get(name=tag, category="type")
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_primary_muscle_tags(self, session: Session, exercise_id: int, tags: list[str]):
        """Get the tags for a specific primary muscle."""
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        tag_repo = TrueCoachTagRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="primary_muscle")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="primary_muscle"))
                session.commit()
                instance = tag_repo.get(name=tag, category="primary_muscle")
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_secondary_muscle_tags(self, session: Session, exercise_id: int, tags: list[str]):
        """Get the tags for a specific secondary muscle."""
        exercise_tags = TrueCoachExerciseTagsRepository(session=session)
        tag_repo = TrueCoachTagRepository(session=session)
        for tag in tags:
            instance = tag_repo.get(name=tag, category="secondary_muscle")
            if not instance:
                tag_repo.add(TrueCoachTag(name=tag, category="secondary_muscle"))
                session.commit()
                instance = tag_repo.get(name=tag, category="secondary_muscle")
            exercise_tags.insert_ignore(
                TrueCoachExerciseTags(exercise_id=exercise_id, tag_id=instance.id)
            )

    def add_workout_item(self, session: Session, workout_item: WorkoutItem):
        """Add a new workout item."""
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

    def update_workout_item(self, session: Session, workout_item: PutWorkoutItemRequest):
        """Add a new workout item."""
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

    def add_workout(self, session: Session, workout: Workout):
        """Add a new workout."""
        # Remove old workout items
        if workout.workout_item_ids:
            self.remove_old_workout_items(
                session=session, workout_id=workout.id, workout_items=workout.workout_item_ids
            )

        workout_repo = TrueCoachWorkoutRepository(session=session)
        instance = TrueCoachWorkout(
            id=workout.id,
            title=workout.title,
            due=datetime.strptime(workout.due, "%Y-%m-%d"),
            short_description=workout.short_description,
            state=workout.state,
            rest_day=workout.rest_day,
            created_at=datetime.strptime(workout.created_at, "%Y-%m-%dT%H:%M:%S.%fZ"),
            updated_at=datetime.strptime(workout.updated_at, "%Y-%m-%dT%H:%M:%S.%fZ"),
        )
        workout_repo.merge(instance)

    def remove_old_workout_items(self, session: Session, workout_id: int, workout_items: list[int]):
        """Remove old workout items."""
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
            .filter(WorkoutItemTrackerModel.true_coach_id.in_(tc_subq))
            .subquery()
        )

        # Delete SETS records where workout_item_id is in the list of WorkoutItem IDs.
        session.query(SetsTrackerModel).filter(
            SetsTrackerModel.workout_item_id.in_(wi_subq)
        ).delete(synchronize_session=False)

        # Delete WorkoutItem records.
        session.query(WorkoutItemTrackerModel).filter(
            WorkoutItemTrackerModel.id.in_(wi_subq)
        ).delete(synchronize_session=False)

        # Delete TrueCoachWorkoutItem records.
        session.query(TrueCoachWorkoutItem).filter(TrueCoachWorkoutItem.id.in_(tc_subq)).delete(
            synchronize_session=False
        )

        # Commit the transaction.
        session.commit()

    def get_workout(self, session: Session, **kwargs: Any):
        """Get a workout by id."""
        workout_repo = TrueCoachWorkoutRepository(session=session)
        return workout_repo.get(**kwargs)

    def get_workout_item(self, session: Session, **kwargs: Any):
        """Get a workout item by kwargs"""
        workout_item_repo = TrueCoachWorkoutItemRepository(session=session)
        return workout_item_repo.get(**kwargs)

    def get_workout_items(self, session: Session, **kwargs: Any):
        """Get a list of workout items"""
        workout_item_repo = TrueCoachWorkoutItemRepository(session=session)
        return workout_item_repo.get_all(**kwargs)

    def add_assessment_item(self, session: Session, assessment: AssessmentItem):
        """Add a new assessment item."""
        assessment_repo = TrueCoachAssessmentItemRepository(session=session)
        instance = TrueCoachAssessmentItem(
            id=assessment.id,
            assessment_id=assessment.assessment_id,
            value=assessment.value,
            note=assessment.note,
            created_at=datetime.strptime(assessment.created_at, "%Y-%m-%dT%H:%M:%S.%fZ"),
            updated_at=datetime.strptime(assessment.updated_at, "%Y-%m-%dT%H:%M:%S.%fZ"),
            date=datetime.strptime(assessment.date, "%Y-%m-%dT%H:%M:%S.%fZ"),
            completed_date=datetime.strptime(assessment.completed_date, "%Y-%m-%d"),
        )
        assessment_repo.merge(instance)

    def _add_assessment(self, session: Session, assessment: Assessment):
        """Add a new assessment."""
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
            created_at=datetime.strptime(assessment.created_at, "%Y-%m-%dT%H:%M:%S.%fZ"),
            updated_at=datetime.strptime(assessment.updated_at, "%Y-%m-%dT%H:%M:%S.%fZ"),
        )
        assessment_repo.merge(instance)

    def add_assessment(self, assessment: AssessmentResponse):
        """Add a new assessment."""
        with self.get_session() as session:
            self._add_assessment(session=session, assessment=assessment.assessment)
            for assessment_item in assessment.assessment_items:
                self.add_assessment_item(session=session, assessment=assessment_item)
            session.commit()

    def delete_workout(self, session: Session, workout: TrueCoachWorkout):
        """Delete a workout by id."""
        workout_repo = TrueCoachWorkoutRepository(session=session)
        workout_repo.delete(workout)
        session.commit()
