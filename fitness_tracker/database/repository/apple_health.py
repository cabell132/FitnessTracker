from sqlalchemy.orm import Session

from fitness_tracker.database.models.apple_health import (
    AppleHealthDataRecord,
    AppleHealthDataType,
    AppleHealthWorkoutType,
    AppleHealthWorkout
)
from fitness_tracker.database.repository.base import BaseRepository


class AppleHealthDataTypeRepository(BaseRepository[AppleHealthDataType]):
    """Apple Health Data Type repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the Apple Health Data Type repository with the session."""
        super().__init__(session=session, model_class=AppleHealthDataType)


class AppleHealthDataRecordRepository(BaseRepository[AppleHealthDataRecord]):
    """Apple Health Data Record repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the Apple Health Data Record repository with the session."""
        super().__init__(session=session, model_class=AppleHealthDataRecord)


class AppleHealthWorkoutTypeRepository(BaseRepository[AppleHealthWorkoutType]):
    """Apple Health Workout Type repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the Apple Health Workout Type repository with the session."""
        super().__init__(session=session, model_class=AppleHealthWorkoutType)

class AppleHealthWorkoutRepository(BaseRepository[AppleHealthWorkout]):
    """Apple Health Workout repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the Apple Health Workout repository with the session."""
        super().__init__(session=session, model_class=AppleHealthWorkout)
