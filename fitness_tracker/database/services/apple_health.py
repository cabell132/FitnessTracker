import re
from datetime import datetime, timezone
from typing import Optional

from pandas import DataFrame
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql import select

from fitness_tracker.database.models.apple_health import (
    AppleHealthDataRecord,
    AppleHealthDataType,
    AppleHealthWorkout,
    AppleHealthWorkoutType,
)
from fitness_tracker.database.repository.apple_health import (
    AppleHealthDataRecordRepository,
    AppleHealthDataTypeRepository,
    AppleHealthWorkoutRepository,
    AppleHealthWorkoutTypeRepository,
)
from fitness_tracker.database.services.base import BaseService


class AppleHealthService(BaseService):
    """Apple Health database service class."""

    def __init__(self, engine: Engine) -> None:
        """Initiate the Apple Health service with the engine."""
        super().__init__(engine)

    def add_data_type(self, session: Session, column: str) -> Optional[AppleHealthDataType]:
        """Add a list of data types."""
        repo = AppleHealthDataTypeRepository(session=session)
        match = re.search(r"\((.*?)\)", column)
        if match:
            unit = match.group(1)
            # Extract the column name without the unit
            name = re.sub(r"\(.*?\)", "", column).strip()
            entry = AppleHealthDataType(name=name, unit=unit)

            repo.insert_ignore(entry)
            session.commit()

            return repo.get(name=name, unit=unit)
        return None

    def add_data_record(
        self, session: Session, data_type_id: int, timestamp: datetime, value: float
    ) -> None:
        """Add a data record."""
        repo = AppleHealthDataTypeRepository(session=session)
        data_record = AppleHealthDataRecord(
            data_type_id=data_type_id, value=value, timestamp=timestamp
        )
        repo = AppleHealthDataRecordRepository(session=session)
        repo.insert_ignore(data_record)

    def add_data_records(self, df: DataFrame) -> None:
        """Add a list of data records."""
        with self.get_session() as session:
            for column in df.columns:
                data_type = self.add_data_type(session, column)
                if data_type:
                    for timestamp, row in df.iterrows():
                        self.add_data_record(
                            session=session,
                            data_type_id=data_type.id,
                            timestamp=timestamp,
                            value=row[column],
                        )
            session.commit()

    def add_workout_type(self, session: Session, name: str) -> Optional[AppleHealthWorkoutType]:
        """Add a workout type."""
        repo = AppleHealthWorkoutTypeRepository(session=session)
        entry = AppleHealthWorkoutType(name=name)

        repo.insert_ignore(entry)
        session.commit()

        return repo.get(name=name)

    def add_workout(
        self, session: Session, workout_type_id: int, start_date: datetime, end_date: datetime
    ) -> None:
        """Add a workout."""
        repo = AppleHealthWorkoutRepository(session=session)
        workout = AppleHealthWorkout(
            workout_type_id=workout_type_id, start_date=start_date, end_date=end_date
        )
        repo.insert_ignore(workout)
        session.commit()

    def add_workouts(self, df: DataFrame) -> None:
        """Add a list of workouts."""
        with self.get_session() as session:
            for _, row in df.iterrows():
                workout_type = self.add_workout_type(session, row["Type"])
                if workout_type:
                    start_date = datetime.strptime(row["Start"], "%Y-%m-%d %H:%M")
                    end_date = datetime.strptime(row["End"], "%Y-%m-%d %H:%M")
                    self.add_workout(
                        session=session,
                        workout_type_id=workout_type.id,
                        start_date=start_date,
                        end_date=end_date,
                    )
            session.commit()

    def get_body_fat_percentage(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict[datetime, float]]:
        """Get the body fat percentage."""
        if start_date is None:
            start_date = datetime(1970, 1, 1, tzinfo=timezone.utc)
        if end_date is None:
            end_date = datetime.now(tz=timezone.utc)
        stmnt = (
            select(AppleHealthDataRecord)
            .join(AppleHealthDataType, AppleHealthDataRecord.data_type_id == AppleHealthDataType.id)
            .where(
                AppleHealthDataType.name == "Body Fat Percentage",
                AppleHealthDataRecord.timestamp.between(start_date, end_date),
            )
        )
        with self.get_session() as session:
            result = session.execute(stmnt).scalars().all()
            return [{"timestamp": record.timestamp, "value": record.value} for record in result]
