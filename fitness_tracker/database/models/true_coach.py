from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.sql import func

from fitness_tracker.database.models.base import BaseModel

if TYPE_CHECKING:
    from fitness_tracker.database.models.hevy_app import HevyAppExercise, HevyAppWorkout
    from fitness_tracker.database.models.tracker import Exercise, Workout, WorkoutItem

# Association table for many-to-many relationship between Exercise and Tag


class TrueCoachWorkout(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=False)  # API provides id
    title = Column(String, nullable=True)
    due = Column(DateTime, nullable=True)
    short_description = Column(Text, nullable=True)
    state = Column(String, nullable=True)
    rest_day = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    # Relationships
    workout_items: Mapped[list["TrueCoachWorkoutItem"]] = relationship(
        "TrueCoachWorkoutItem", back_populates="workout", cascade="all, delete-orphan"
    )
    tracker: Mapped[Optional["Workout"]] = relationship(
        "Workout", foreign_keys="Workout.true_coach_id", uselist=False, cascade="all, delete-orphan"
    )
    hevy_app: Mapped[Optional["HevyAppWorkout"]] = relationship(
        "HevyAppWorkout",
        secondary="Workout",
        primaryjoin="TrueCoachWorkout.id == Workout.true_coach_id",
        secondaryjoin="HevyAppWorkout.id == Workout.hevy_app_id",
        overlaps="tracker",
    )

    def __repr__(self) -> str:
        """Returns a string representation of the TrueCoachWorkout instance.

        Returns:
            str: A string containing the id, title, due date, short description, state, rest day status,
                 creation date, and last updated date of the workout.
        """  # noqa: W505
        return f"<TrueCoachWorkout id={self.id} title={self.title} due={self.due} short_description={self.short_description} state={self.state} rest_day={self.rest_day} created_at={self.created_at} updated_at={self.updated_at}>"


class TrueCoachWorkoutItem(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=False)  # API provides id
    workout_id = Column(Integer, ForeignKey("TrueCoachWorkout.id"), nullable=False)
    name = Column(String, nullable=False)
    info = Column(String, nullable=True)
    comment = Column(String, nullable=True)
    is_circuit = Column(Boolean, default=False)
    state = Column(String, nullable=False)
    position = Column(Integer, nullable=True)
    exercise_id = Column(
        Integer, ForeignKey("TrueCoachExercise.id"), nullable=True
    )  # Links to the Exercise table
    assessment_id = Column(Integer, nullable=True)

    # Relationships
    workout: Mapped["TrueCoachWorkout"] = relationship(
        "TrueCoachWorkout", back_populates="workout_items"
    )
    exercise: Mapped[Optional["TrueCoachExercise"]] = relationship("TrueCoachExercise")
    tracker: Mapped[Optional["WorkoutItem"]] = relationship(
        "WorkoutItem",
        foreign_keys="WorkoutItem.true_coach_id",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<TrueCoachWorkoutItem id={self.id} workout_id={self.workout_id} name={self.name} info={self.info} comment={self.comment} is_circuit={self.is_circuit} state={self.state} position={self.position} exercise_id={self.exercise_id} assessment_id={self.assessment_id}>"


class TrueCoachExercise(BaseModel):
    __tablename__: str = __qualname__

    id = Column(
        Integer, primary_key=True, autoincrement=False
    )  # Non-auto increment due to API data
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    url = Column(String, nullable=True)
    video_partner_name = Column(String, nullable=True)
    default = Column(Boolean, default=False)

    # Relationships
    tags: Mapped[Optional[list["TrueCoachTag"]]] = relationship(
        "TrueCoachTag", secondary="TrueCoachExerciseTags", back_populates="exercises"
    )
    tracker: Mapped[Optional["Exercise"]] = relationship(
        "Exercise", foreign_keys="Exercise.true_coach_id"
    )
    hevy_app: Mapped[Optional["HevyAppExercise"]] = relationship(
        "HevyAppExercise",
        secondary="Exercise",
        uselist=False,
        primaryjoin="TrueCoachExercise.id == Exercise.true_coach_id",
        secondaryjoin="HevyAppExercise.id == Exercise.hevy_app_id",
        overlaps="tracker",
    )

    def __repr__(self) -> str:
        return f"<TrueCoachExercise id={self.id} name={self.name} description={self.description} url={self.url} video_partner_name={self.video_partner_name} default={self.default}>"


class TrueCoachTag(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # e.g., 'pattern', 'plane', 'level'

    # Relationship
    exercises: Mapped[Optional[list["TrueCoachExercise"]]] = relationship(
        "TrueCoachExercise", secondary="TrueCoachExerciseTags", back_populates="tags"
    )

    def __repr__(self) -> str:
        return f"<TrueCoachTag id={self.id} name={self.name} category={self.category}>"


class TrueCoachExerciseTags(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    exercise_id = Column(Integer, ForeignKey("TrueCoachExercise.id"), nullable=False)
    tag_id = Column(Integer, ForeignKey("TrueCoachTag.id"), nullable=False)

    # Relationships
    exercise: Mapped["TrueCoachExercise"] = relationship("TrueCoachExercise", overlaps="exercises,tags")
    tag: Mapped["TrueCoachTag"] = relationship("TrueCoachTag", overlaps="exercises,tags")

    def __repr__(self) -> str:
        return f"<TrueCoachExerciseTags id={self.id} exercise_id={self.exercise_id} tag_id={self.tag_id}>"


class TrueCoachAssessment(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=False)
    assessment_group_id = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    units = Column(String, nullable=False)
    order = Column(Integer, nullable=False)
    target = Column(String, nullable=True)
    target_percentage = Column(String, nullable=True)
    linked_assessment_id = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    # Relationships

    assessment_items: Mapped[Optional[list["TrueCoachAssessmentItem"]]] = relationship(
        "TrueCoachAssessmentItem", back_populates="assessment"
    )

    def __repr__(self) -> str:
        return f"<TrueCoachAssessment id={self.id} assessment_group_id={self.assessment_group_id} name={self.name} units={self.units} order={self.order} target={self.target} target_percentage={self.target_percentage} linked_assessment_id={self.linked_assessment_id} updated_at={self.updated_at} created_at={self.created_at}>"


class TrueCoachAssessmentItem(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=False)
    assessment_id = Column(Integer, ForeignKey("TrueCoachAssessment.id"), nullable=False)
    value = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)
    date = Column(DateTime, nullable=True)
    completed_date = Column(DateTime, nullable=True)

    # Relationships
    assessment: Mapped["TrueCoachAssessment"] = relationship(
        "TrueCoachAssessment", back_populates="assessment_items"
    )

    def __repr__(self) -> str:
        return f"<TrueCoachAssessmentItem id={self.id} assessment_id={self.assessment_id} value={self.value} note={self.note} created_at={self.created_at} updated_at={self.updated_at} date={self.date} completed_date={self.completed_date}>"
