from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
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

from fitness_tracker.database.models.base import BaseModel

if TYPE_CHECKING:
    from fitness_tracker.database.models.hevy_app import (
        HevyAppExercise,
        HevyAppSets,
        HevyAppWorkout,
        HevyAppWorkoutItem,
    )
    from fitness_tracker.database.models.apple_health import AppleHealthDataRecord
    from fitness_tracker.database.models.true_coach import (
        TrueCoachExercise,
        TrueCoachWorkout,
        TrueCoachWorkoutItem,
        TrueCoachAssessment,
        TrueCoachAssessmentItem,
    )


# Association table for many-to-many relationship between Exercise and Tag
class Workout(BaseModel):
    """Represents a workout in the fitness tracker database.

    Attributes:
        __tablename__ (str): The name of the table in the database.
        id (int): The primary key of the workout.
        title (str): The title of the workout.
        description (str): A detailed description of the workout.
        hevy_app_id (str, optional): The foreign key linking to a HevyAppWorkout.
        true_coach_id (int, optional): The foreign key linking to a TrueCoachWorkout.
        workout_items (list[WorkoutItem]): The list of workout items associated with this workout.
        hevy_app (Optional[HevyAppWorkout]): The associated HevyAppWorkout, if any.
        true_coach (Optional[TrueCoachWorkout]): The associated TrueCoachWorkout, if any.
    Constraints:
        __table_args__: A unique constraint ensuring that the combination of hevy_app_id and true_coach_id is unique.
    """  # noqa: W505

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    hevy_app_id = Column(String, ForeignKey("HevyAppWorkout.id"), nullable=True)
    true_coach_id = Column(Integer, ForeignKey("TrueCoachWorkout.id"), nullable=True)

    # Relationships
    workout_items: Mapped[list["WorkoutItem"]] = relationship(
        "WorkoutItem", back_populates="workout"
    )
    hevy_app: Mapped[Optional["HevyAppWorkout"]] = relationship("HevyAppWorkout", overlaps="hevy_app,true_coach")
    true_coach: Mapped[Optional["TrueCoachWorkout"]] = relationship("TrueCoachWorkout", overlaps="hevy_app,tracker,true_coach")

    # Constraints
    __table_args__ = (
        UniqueConstraint("hevy_app_id", "true_coach_id", name="_hevy_app_true_coach_uc"),
        UniqueConstraint("hevy_app_id", name="_hevy_app_uc"),
        UniqueConstraint("true_coach_id", name="_true_coach_uc"),
    )


class WorkoutItem(BaseModel):
    """Represents an item in a workout, including details about the exercise, position, and associated apps.

    Attributes:
        id (int): The primary key of the workout item.
        workout_id (int): Foreign key referencing the associated workout.
        position (int): The position of the workout item within the workout.
        exercise_id (int): Foreign key referencing the associated exercise.
        hevy_app_id (Optional[int]): Foreign key referencing the associated Hevy app workout item.
        true_coach_id (Optional[int]): Foreign key referencing the associated TrueCoach workout item.
        rest (int): The rest period after the workout item.
    Relationships:
        workout (Workout): The associated workout.
        exercise (Exercise): The associated exercise.
        hevy_app (Optional[HevyAppWorkoutItem]): The associated Hevy app workout item.
        true_coach (Optional[TrueCoachWorkoutItem]): The associated TrueCoach workout item.
    """  # noqa: W505

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    workout_id = Column(Integer, ForeignKey("Workout.id"), nullable=False)
    position = Column(Integer, nullable=False)
    exercise_id = Column(Integer, ForeignKey("Exercise.id"), nullable=False)
    hevy_app_id = Column(Integer, ForeignKey("HevyAppWorkoutItem.id"), nullable=True)
    true_coach_id = Column(Integer, ForeignKey("TrueCoachWorkoutItem.id"), nullable=True)
    rest = Column(Integer, nullable=False, default=90)

    # Relationships
    workout: Mapped["Workout"] = relationship("Workout", back_populates="workout_items")
    exercise: Mapped["Exercise"] = relationship("Exercise")
    hevy_app: Mapped[Optional["HevyAppWorkoutItem"]] = relationship(
        "HevyAppWorkoutItem", uselist=False, overlaps="true_coach"
    )
    true_coach: Mapped[Optional["TrueCoachWorkoutItem"]] = relationship(
        "TrueCoachWorkoutItem", uselist=False, overlaps="tracker,true_coach"
    )
    sets: Mapped[list["Sets"]] = relationship(
        "Sets", back_populates="workout_item", cascade="all, delete-orphan"
    )


class Exercise(BaseModel):
    """Represents an exercise in the fitness tracker database.

    Attributes:
        id (int): The primary key for the exercise.
        name (str): The name of the exercise.
        hevy_app_id (str): The foreign key referencing the HevyAppExercise table.
        true_coach_id (int): The foreign key referencing the TrueCoachExercise table.
        hevy_app (HevyAppExercise): The relationship to the HevyAppExercise model.
        true_coach (TrueCoachExercise): The relationship to the TrueCoachExercise model.
    Constraints:
        __table_args__ (tuple): Unique constraint on the combination of hevy_app_id and true_coach_id.
    """  # noqa: W505

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    hevy_app_id = Column(
        String,
        ForeignKey("HevyAppExercise.id"),
        nullable=True,
        default=None,
    )
    true_coach_id = Column(Integer, ForeignKey("TrueCoachExercise.id"), nullable=True)

    # Relationships
    hevy_app: Mapped["HevyAppExercise"] = relationship("HevyAppExercise", overlaps="hevy_app,true_coach")
    true_coach: Mapped["TrueCoachExercise"] = relationship("TrueCoachExercise", overlaps="hevy_app,tracker,true_coach")

    # Constraints
    __table_args__ = (
        UniqueConstraint("hevy_app_id", "true_coach_id", name="_hevy_app_true_coach_uc"),
        UniqueConstraint("name", name="_name_uc"),
    )


class Sets(BaseModel):
    """Represents a set of exercises within a workout item.

    Attributes:
        id (int): The unique identifier for the set.
        workout_item_id (int): The foreign key referencing the associated workout item.
        index (int): The index of the set within the workout item.
        type (str): The type of exercise performed in the set.
        weight_kg (float, optional): The weight used in the set, in kilograms.
        reps (int, optional): The number of repetitions performed in the set.
        distance_meters (int, optional): The distance covered in the set, in meters.
        duration_seconds (int, optional): The duration of the set, in seconds.
        rpe (int, optional): The rate of perceived exertion for the set.
        hevy_app_id (int, optional): The foreign key referencing the associated Hevy app set.
    Relationships:
        workout_item (WorkoutItem): The associated workout item.
        hevy_app (Optional[HevyAppSets]): The associated Hevy app set, if any.
    Constraints:
        __table_args__ (tuple): Unique constraint on workout_item_id, index, and hevy_app_id.

    Methods:
        __repr__() -> str: Returns a string representation of the object.
    """

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    workout_item_id = Column(Integer, ForeignKey("WorkoutItem.id"), nullable=False)
    index = Column(Integer, nullable=False)
    type = Column(String, nullable=False)
    weight_kg = Column(Float, nullable=True)
    reps = Column(Integer, nullable=True)
    distance_meters = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    rpe = Column(Integer, nullable=True)
    hevy_app_id = Column(Integer, ForeignKey("HevyAppSets.id"), nullable=True)

    # Relationships
    workout_item: Mapped["WorkoutItem"] = relationship(
        "WorkoutItem", back_populates="sets", uselist=False
    )
    hevy_app: Mapped[Optional["HevyAppSets"]] = relationship("HevyAppSets", uselist=False)

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "workout_item_id", "index", "hevy_app_id", name="_hevy_app_workout_item_index_uc"
        ),
        UniqueConstraint("workout_item_id", "index", name="_workout_item_index_uc"),
    )

    def __repr__(self) -> str:
        """Return a string representation of the object."""
        return f"<HevyAppWorkoutSets id={self.id} workout_item_id={self.workout_item_id} index={self.index} type={self.type} weight_kg={self.weight_kg} reps={self.reps} distance_meters={self.distance_meters} duration_seconds={self.duration_seconds} rpe={self.rpe}>"


class Metric(BaseModel):
    """Represents a metric in the fitness tracker database.

    Attributes:
        id (int): The primary key for the metric.
        name (str): The name of the metric.
        unit (str): The unit of measurement for the metric.
        hevy_app_id (str): The foreign key referencing the HevyAppMetric table.
        true_coach_id (int): The foreign key referencing the TrueCoachMetric table.
        hevy_app (HevyAppMetric): The relationship to the HevyAppMetric model.
        true_coach (TrueCoachMetric): The relationship to the TrueCoachMetric model.
    Constraints:
        __table_args__ (tuple): Unique constraint on the combination of hevy_app_id and true_coach_id.
    """  # noqa: W505

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    unit = Column(String, nullable=True)
    true_coach_id = Column(Integer, ForeignKey("TrueCoachAssessment.id"), nullable=True)

    # Relationships
    true_coach: Mapped["TrueCoachAssessment"] = relationship("TrueCoachAssessment")
    metric_items: Mapped[list["MetricItem"]] = relationship("MetricItem", back_populates="metric")

    # Constraints
    __table_args__ = (
        UniqueConstraint("name", name="_name_uc"),
        UniqueConstraint("true_coach_id", name="_true_coach_uc"),
    )


class MetricItem(BaseModel):
    """Represents a metric item in the fitness tracker database.

    Attributes:
        id (int): The primary key for the metric item.
        metric_id (int): The foreign key referencing the Metric table.
        value (float): The value of the metric.
        unit (str): The unit of measurement for the metric.
        date (datetime): The date and time when the metric was recorded.

    Constraints:
        __table_args__ (tuple): Unique constraint on workout_item_id, metric_id, and hevy_app_id.
    """

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_id = Column(Integer, ForeignKey("Metric.id"), nullable=False)
    value = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)
    true_coach_id = Column(Integer, ForeignKey("TrueCoachAssessmentItem.id"), nullable=True)
    apple_id = Column("apple_id", Integer, ForeignKey("AppleHealthDataRecord.id"), nullable=True)
    workout_id = Column(Integer, ForeignKey("Workout.id"), nullable=True)

    # Relationships
    metric: Mapped["Metric"] = relationship("Metric", back_populates="metric_items")
    true_coach: Mapped["TrueCoachAssessmentItem"] = relationship(
        "TrueCoachAssessmentItem", uselist=False
    )
    apple_health: Mapped["AppleHealthDataRecord"] = relationship(
        "AppleHealthDataRecord", uselist=False
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("apple_id", name="_apple_id"),
        UniqueConstraint("true_coach_id", name="_true_coach_id"),
        UniqueConstraint("workout_id", "metric_id", name="_workout_id_metric_id"),
    )
