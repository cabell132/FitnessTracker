"""Repositories for Apple Health ORM tables."""

from sqlalchemy.orm import Session

from fitness_tracker.database.models.apple_health import (
    AppleHealthDataRecord,
    AppleHealthDataType,
    AppleHealthWorkout,
    AppleHealthWorkoutType,
)
from fitness_tracker.database.repository.base import BaseRepository


class AppleHealthDataTypeRepository(BaseRepository[AppleHealthDataType]):
    """Persistence access for :class:`AppleHealthDataType` rows."""

    def __init__(self, session: Session) -> None:
        """Create a data-type repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=AppleHealthDataType)


class AppleHealthDataRecordRepository(BaseRepository[AppleHealthDataRecord]):
    """Persistence access for :class:`AppleHealthDataRecord` rows."""

    def __init__(self, session: Session) -> None:
        """Create a data-record repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=AppleHealthDataRecord)


class AppleHealthWorkoutTypeRepository(BaseRepository[AppleHealthWorkoutType]):
    """Persistence access for :class:`AppleHealthWorkoutType` rows."""

    def __init__(self, session: Session) -> None:
        """Create a workout-type repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=AppleHealthWorkoutType)


class AppleHealthWorkoutRepository(BaseRepository[AppleHealthWorkout]):
    """Persistence access for :class:`AppleHealthWorkout` rows."""

    def __init__(self, session: Session) -> None:
        """Create a workout repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=AppleHealthWorkout)
