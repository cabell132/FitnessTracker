"""Apple Health domain repository operations."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, cast

from pandas import DataFrame, Timestamp
from sqlalchemy import select

from fitness_tracker.database.models.apple_health import (
    AppleHealthDataRecord,
    AppleHealthDataType,
    AppleHealthWorkout,
    AppleHealthWorkoutType,
)
from fitness_tracker.database.uow.base import CrudMixin


class AppleHealthMixin(CrudMixin):
    """Apple Health persistence helper methods."""

    def ah_add_data_type(self, column: str) -> AppleHealthDataType | None:
        """Parse a CSV column header into a data type and persist it.

        Args:
            column (str): Header like ``"Steps (count)"`` with optional ``(unit)`` suffix.

        Returns:
            AppleHealthDataType | None: Row after insert, or None if lacking a unit.
        """
        match = re.search(r"\((.*?)\)", column)
        if match:
            unit = match.group(1)
            name = re.sub(r"\(.*?\)", "", column).strip()
            entry = AppleHealthDataType(name=name, unit=unit)
            self.insert_ignore(entry)
            self.flush()
            return self.get(AppleHealthDataType, name=name, unit=unit)
        return None

    def ah_add_data_record(
        self,
        data_type_id: int,
        timestamp: datetime,
        value: float,
    ) -> None:
        """Insert one sampled metric row for an existing data type.

        Args:
            data_type_id (int): Parent data type id.
            timestamp (datetime): Sample time.
            value (float): Numeric sample value.
        """
        data_record = AppleHealthDataRecord(
            data_type_id=data_type_id,
            value=value,
            timestamp=timestamp,
        )
        self.insert_ignore(data_record)

    def ah_add_data_records(self, df: DataFrame) -> None:
        """Bulk-load metric samples from a wide CSV-style dataframe.

        Args:
            df (DataFrame): Columns are metric headers; index is timestamps.
        """
        for column in df.columns:
            data_type = self.ah_add_data_type(column)
            if data_type:
                for timestamp, row in df.iterrows():
                    ts = Timestamp(cast(Any, timestamp)).to_pydatetime()
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    self.ah_add_data_record(
                        data_type_id=cast(int, data_type.id),
                        timestamp=ts,
                        value=float(row[column]),
                    )

    def ah_add_workout_type(self, name: str) -> AppleHealthWorkoutType | None:
        """Insert or fetch a workout category label.

        Args:
            name (str): Label from the export (e.g. running, cycling).

        Returns:
            AppleHealthWorkoutType | None: Row after insert, or None if lookup failed.
        """
        entry = AppleHealthWorkoutType(name=name)
        self.insert_ignore(entry)
        self.flush()
        return self.get(AppleHealthWorkoutType, name=name)

    def ah_add_workout(
        self,
        workout_type_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> None:
        """Persist one workout interval for a known workout type.

        Args:
            workout_type_id (int): Foreign key to the workout type.
            start_date (datetime): Interval start.
            end_date (datetime): Interval end.
        """
        workout = AppleHealthWorkout(
            workout_type_id=workout_type_id,
            start_date=start_date,
            end_date=end_date,
        )
        self.insert_ignore(workout)

    def ah_add_workouts(self, df: DataFrame) -> None:
        """Bulk-load workouts from an Apple Health export dataframe.

        Args:
            df (DataFrame): Must include ``Type``, ``Start``, and ``End`` columns.
        """
        for _, row in df.iterrows():
            workout_type = self.ah_add_workout_type(row["Type"])
            if workout_type:
                start_date = datetime.strptime(
                    row["Start"],
                    "%Y-%m-%d %H:%M",
                ).replace(tzinfo=UTC)
                end_date = datetime.strptime(
                    row["End"],
                    "%Y-%m-%d %H:%M",
                ).replace(tzinfo=UTC)
                self.ah_add_workout(
                    workout_type_id=cast(int, workout_type.id),
                    start_date=start_date,
                    end_date=end_date,
                )

    def ah_get_body_fat_percentage(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, datetime | float]]:
        """Query body fat percentage samples in a time range.

        Args:
            start_date (datetime | None): Inclusive range start. Defaults to epoch UTC.
            end_date (datetime | None): Inclusive range end. Defaults to now UTC.

        Returns:
            list[dict[str, datetime | float]]: Rows with ``timestamp`` and ``value``.
        """
        if start_date is None:
            start_date = datetime(1970, 1, 1, tzinfo=UTC)
        if end_date is None:
            end_date = datetime.now(tz=UTC)
        stmnt = (
            select(AppleHealthDataRecord)
            .join(
                AppleHealthDataType,
                AppleHealthDataRecord.data_type_id == AppleHealthDataType.id,
            )
            .where(
                AppleHealthDataType.name == "Body Fat Percentage",
                AppleHealthDataRecord.timestamp.between(start_date, end_date),
            )
        )
        result = self._session.execute(stmnt).scalars().all()
        return [
            {
                "timestamp": cast(datetime, record.timestamp),
                "value": float(record.value),
            }
            for record in result
        ]
