from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.sql import func

from fitness_tracker.database.models.base import BaseModel

if TYPE_CHECKING:

    from fitness_tracker.database.models.true_coach import TrueCoachWorkout, TrueCoachExercise, TrueCoachWorkoutItem


# Association table for many-to-many relationship between Exercise and Tag
class HevyAppWorkout(BaseModel):
    """Represents a workout in the Hevy app.

    Attributes:
        __tablename__ (str): The name of the table in the database.
        id (str): The unique identifier for the workout.
        title (str): The title of the workout.
        description (str): A detailed description of the workout.
        start_time (datetime): The start time of the workout.
        end_time (datetime): The end time of the workout.
        created_at (datetime): The timestamp when the workout was created.
        updated_at (datetime): The timestamp when the workout was last updated.
    Relationships:
        workout_items (list[HevyAppWorkoutItem]): The list of workout items associated with this workout.

    Methods:
        __repr__() -> str: Returns the string representation of the object.
    """  # noqa: W505

    __tablename__: str = __qualname__

    id = Column(String, primary_key=True, autoincrement=False)  # API provides id
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    # Relationships
    workout_items: Mapped[list["HevyAppWorkoutItem"]] = relationship(
        "HevyAppWorkoutItem", back_populates="workout", cascade="all, delete-orphan"
    )
    true_coach: Mapped[Optional["TrueCoachWorkout"]] = relationship(
        "TrueCoachWorkout", secondary="Workout", uselist=False, overlaps="hevy_app,tracker"
    )

    def __repr__(self) -> str:
        """Return the string representation of the object."""
        return f"<HevyAppWorkout id={self.id} title={self.title} description={self.description} start_time={self.start_time} end_time={self.end_time} created_at={self.created_at} updated_at={self.updated_at}>"


class HevyAppWorkoutItem(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)  # API provides id
    workout_id = Column(Integer, ForeignKey("HevyAppWorkout.id"), nullable=False)
    index = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    notes = Column(String, nullable=False)
    superset_id = Column(Integer, default=False)
    exercise_id = Column(
        String, ForeignKey("HevyAppExercise.id"), nullable=True
    )  # Links to the Exercise table

    # Relationships
    workout: Mapped["HevyAppWorkout"] = relationship(
        "HevyAppWorkout", back_populates="workout_items"
    )
    true_coach: Mapped[Optional["TrueCoachWorkoutItem"]] = relationship(
        "TrueCoachWorkoutItem", secondary="WorkoutItem", uselist=False, overlaps="tracker"
    )
    exercise: Mapped["HevyAppExercise"] = relationship("HevyAppExercise")
    sets: Mapped[list["HevyAppSets"]] = relationship(
        "HevyAppSets", back_populates="workout_item", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (UniqueConstraint("workout_id", "index", name="_hevy_app_workout_index_uc"),)

    def __repr__(self) -> str:
        return f"<HevyAppWorkoutItem id={self.id} workout_id={self.workout_id} index={self.index} name={self.name} notes={self.notes} superset_id={self.superset_id} exercise_id={self.exercise_id}>"


class HevyAppSets(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    workout_item_id = Column(Integer, ForeignKey("HevyAppWorkoutItem.id"), nullable=False)
    index = Column(Integer, nullable=False)
    type = Column(String, nullable=False)
    weight_kg = Column(Float, nullable=True)
    reps = Column(Integer, nullable=True)
    distance_meters = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    rpe = Column(Integer, nullable=True)

    # Relationships
    workout_item: Mapped["HevyAppWorkoutItem"] = relationship(
        "HevyAppWorkoutItem", back_populates="sets"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("workout_item_id", "index", name="_hevy_app_workout_item_index_uc"),
    )

    def __repr__(self) -> str:
        return f"<HevyAppWorkoutSets id={self.id} workout_item_id={self.workout_item_id} index={self.index} type={self.type} weight_kg={self.weight_kg} reps={self.reps} distance_meters={self.distance_meters} duration_seconds={self.duration_seconds} rpe={self.rpe}>"


class HevyAppExercise(BaseModel):
    __tablename__: str = __qualname__

    id = Column(String, primary_key=True, autoincrement=False)  # Non-auto increment due to API data
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    equipment = Column(String, nullable=False)
    default = Column(Boolean, default=False)

    # Relationships
    activated_muscles: Mapped[Optional[list["HevyAppActivatedMuscle"]]] = relationship(
        "HevyAppActivatedMuscle", back_populates="exercises"
    )
    workout_items: Mapped[Optional[list["HevyAppWorkoutItem"]]] = relationship(
        "HevyAppWorkoutItem", back_populates="exercise", cascade="all, delete-orphan"
    )
    true_coach: Mapped[Optional["TrueCoachExercise"]] = relationship(
        "TrueCoachExercise", secondary="Exercise", uselist=False, overlaps="hevy_app,tracker"
    )

    def __repr__(self) -> str:
        return f"<HevyAppExercise id={self.id} name={self.name} type={self.type} equipment={self.equipment} default={self.default}>"


class HevyAppActivatedMuscle(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    exercise_id = Column(String, ForeignKey("HevyAppExercise.id"), nullable=False)
    muscle = Column(String, nullable=False)
    category = Column(String, nullable=False)  # e.g., 'primary', 'secondary'

    # Relationship
    exercises: Mapped[Optional[list["HevyAppExercise"]]] = relationship(
        "HevyAppExercise", back_populates="activated_muscles"
    )

    def __repr__(self) -> str:
        return f"<HevyAppActivatedMuscle id={self.id} exercise_id={self.exercise_id} muscle={self.muscle} category={self.category}>"
