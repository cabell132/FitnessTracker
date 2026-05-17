"""ORM models for Apple Health CSV-derived metrics and workouts."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from fitness_tracker.database.models.base import BaseModel


class AppleHealthDataType(BaseModel):
    """A measurable Apple Health series (name + unit)."""

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    unit = Column(String, nullable=False)

    records = relationship("AppleHealthDataRecord", back_populates="data_type")

    __table_args__ = (UniqueConstraint("name", "unit", name="uq_apple_health_type_name_unit"),)


class AppleHealthDataRecord(BaseModel):
    """One sampled value for a data type at a point in time."""

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    data_type_id = Column(Integer, ForeignKey("AppleHealthDataType.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    value = Column(Float, nullable=False)

    data_type = relationship("AppleHealthDataType", back_populates="records")

    __table_args__ = (
        UniqueConstraint("data_type_id", "timestamp", name="uq_apple_health_record_type_timestamp"),
    )


class AppleHealthWorkoutType(BaseModel):
    """Category label for imported Apple Health workouts."""

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    __table_args__ = (UniqueConstraint("name", name="uq_apple_health_workout_type_name"),)


class AppleHealthWorkout(BaseModel):
    """Single workout interval linked to a workout type."""

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    workout_type_id = Column(Integer, ForeignKey("AppleHealthWorkoutType.id"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    workout_type = relationship("AppleHealthWorkoutType")

    __table_args__ = (
        UniqueConstraint(
            "workout_type_id",
            "start_date",
            "end_date",
            name="uq_workout_type_start_date_end_date",
        ),
    )
