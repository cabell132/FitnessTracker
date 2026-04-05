"""Import Apple Health CSV metrics and workouts into the database."""

import re
from datetime import UTC, datetime
from typing import Any, cast

from pandas import DataFrame, Timestamp
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
        """Create the service bound to the given engine.

        Args:
            engine (Engine): SQLAlchemy engine for the tracker database.
        """
        super().__init__(engine)

    def add_data_type(self, session: Session, column: str) -> AppleHealthDataType | None:
        """Parse a CSV column header into a data type and persist it.

        Args:
            session (Session): Active session.
            column (str): Header like ``"Steps (count)"`` with optional ``(unit)`` suffix.

        Returns:
            AppleHealthDataType | None: Row after insert, or None if the header lacked a unit.
        """
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

    def add_data_record(  # noqa: PLR0913
        self, session: Session, data_type_id: int, timestamp: datetime, value: float
    ) -> None:
        """Insert one sampled metric row for an existing data type.

        Args:
            session (Session): Active session.
            data_type_id (int): Parent :class:`AppleHealthDataType` id.
            timestamp (datetime): Sample time (timezone-aware preferred).
            value (float): Numeric sample value.

        Returns:
            None: Nothing is returned; the row is persisted via the session.
        """
        data_record = AppleHealthDataRecord(
            data_type_id=data_type_id, value=value, timestamp=timestamp
        )
        repo = AppleHealthDataRecordRepository(session=session)
        repo.insert_ignore(data_record)

    def add_data_records(self, df: DataFrame) -> None:
        """Bulk-load metric samples from a wide CSV-style dataframe.

        Args:
            df (DataFrame): Columns are metric headers; index is timestamps.

        Returns:
            None: Nothing is returned; the session commits before exit.
        """
        with self.get_session() as session:
            for column in df.columns:
                data_type = self.add_data_type(session, column)
                if data_type:
                    for timestamp, row in df.iterrows():
                        ts = Timestamp(cast(Any, timestamp)).to_pydatetime()
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=UTC)
                        self.add_data_record(
                            session=session,
                            data_type_id=cast(int, data_type.id),
                            timestamp=ts,
                            value=float(row[column]),
                        )
            session.commit()

    def add_workout_type(self, session: Session, name: str) -> AppleHealthWorkoutType | None:
        """Insert or fetch a workout category label.

        Args:
            session (Session): Active session.
            name (str): Label from the export (e.g. running, cycling).

        Returns:
            AppleHealthWorkoutType | None: Row after insert, or None if lookup failed.
        """
        repo = AppleHealthWorkoutTypeRepository(session=session)
        entry = AppleHealthWorkoutType(name=name)

        repo.insert_ignore(entry)
        session.commit()

        return repo.get(name=name)

    def add_workout(  # noqa: PLR0913
        self, session: Session, workout_type_id: int, start_date: datetime, end_date: datetime
    ) -> None:
        """Persist one workout interval for a known workout type.

        Args:
            session (Session): Active session.
            workout_type_id (int): Foreign key to :class:`AppleHealthWorkoutType`.
            start_date (datetime): Interval start (timezone-aware preferred).
            end_date (datetime): Interval end (timezone-aware preferred).

        Returns:
            None: Nothing is returned; the row is persisted via the session.
        """
        repo = AppleHealthWorkoutRepository(session=session)
        workout = AppleHealthWorkout(
            workout_type_id=workout_type_id, start_date=start_date, end_date=end_date
        )
        repo.insert_ignore(workout)
        session.commit()

    def add_workouts(self, df: DataFrame) -> None:
        """Bulk-load workouts from an Apple Health ``export`` dataframe.

        Args:
            df (DataFrame): Must include ``Type``, ``Start``, and ``End`` columns.

        Returns:
            None: Nothing is returned; the session commits before exit.
        """
        with self.get_session() as session:
            for _, row in df.iterrows():
                workout_type = self.add_workout_type(session, row["Type"])
                if workout_type:
                    start_date = datetime.strptime(row["Start"], "%Y-%m-%d %H:%M").replace(
                        tzinfo=UTC
                    )
                    end_date = datetime.strptime(row["End"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
                    self.add_workout(
                        session=session,
                        workout_type_id=cast(int, workout_type.id),
                        start_date=start_date,
                        end_date=end_date,
                    )
            session.commit()

    def get_body_fat_percentage(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, datetime | float]]:
        """Query body fat percentage samples in a time range.

        Args:
            start_date (datetime | None, optional): Inclusive range start. Defaults to epoch UTC.
            end_date (datetime | None, optional): Inclusive range end. Defaults to now UTC.

        Returns:
            list[dict[str, datetime | float]]: Rows with ``timestamp`` and ``value`` keys.
        """
        if start_date is None:
            start_date = datetime(1970, 1, 1, tzinfo=UTC)
        if end_date is None:
            end_date = datetime.now(tz=UTC)
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
            return [
                {
                    "timestamp": cast(datetime, record.timestamp),
                    "value": float(record.value),
                }
                for record in result
            ]
