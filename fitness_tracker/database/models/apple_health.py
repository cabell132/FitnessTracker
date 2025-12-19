from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint
)
from sqlalchemy.orm import relationship

from fitness_tracker.database.models.base import BaseModel


class AppleHealthDataType(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)  # e.g., Steps, Heart Rate, Sleep Duration
    unit = Column(String, nullable=False)  # e.g., "steps", "bpm", "hours"

    records = relationship("AppleHealthDataRecord", back_populates="data_type")

    # Constraints
    __table_args__ = (UniqueConstraint("name", "unit", name="uq_name_unit"),)



class AppleHealthDataRecord(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    data_type_id = Column(Integer, ForeignKey("AppleHealthDataType.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)  # When the data was recorded
    value = Column(Float, nullable=False)  # The value of the health data (e.g., 10000 steps)

    # Relationships
    data_type = relationship("AppleHealthDataType", back_populates="records")

    # Constraints
    __table_args__ = (UniqueConstraint("data_type_id", "timestamp", name="uq_data_type_timestamp"),)

class AppleHealthWorkoutType(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)  # e.g., Steps, Heart Rate, Sleep Duration
    
    # Constraints
    __table_args__ = (UniqueConstraint("name", name="uq_name"),)

class AppleHealthWorkout(BaseModel):
    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    workout_type_id = Column(Integer, ForeignKey("AppleHealthWorkoutType.id"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    # Relationships
    workout_type = relationship("AppleHealthWorkoutType")

    # Constraints
    __table_args__ = (UniqueConstraint("workout_type_id", "start_date", "end_date", name="uq_workout_type_start_date_end_date"),)
