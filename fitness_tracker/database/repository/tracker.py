"""Repositories for unified tracker ORM tables."""

from sqlalchemy.orm import Session

from fitness_tracker.database.models.tracker import Exercise, Sets, Workout, WorkoutItem
from fitness_tracker.database.repository.base import BaseRepository


class FitnessTrackerWorkoutRepository(BaseRepository[Workout]):
    """Persistence access for canonical :class:`Workout` rows."""

    def __init__(self, session: Session) -> None:
        """Create a workout repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=Workout)


class FitnessTrackerExerciseRepository(BaseRepository[Exercise]):
    """Persistence access for canonical :class:`Exercise` rows."""

    def __init__(self, session: Session) -> None:
        """Create an exercise repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=Exercise)


class FitnessTrackerWorkoutItemRepository(BaseRepository[WorkoutItem]):
    """Persistence access for canonical :class:`WorkoutItem` rows."""

    def __init__(self, session: Session) -> None:
        """Create a workout-item repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=WorkoutItem)


class FitnessTrackerSetsRepository(BaseRepository[Sets]):
    """Persistence access for canonical :class:`Sets` rows."""

    def __init__(self, session: Session) -> None:
        """Create a sets repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=Sets)
