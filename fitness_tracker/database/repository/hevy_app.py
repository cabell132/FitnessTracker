"""Repositories for Hevy App ORM tables."""

from sqlalchemy.orm import Session

from fitness_tracker.database.models.hevy_app import (
    HevyAppActivatedMuscle,
    HevyAppExercise,
    HevyAppSets,
    HevyAppWorkout,
    HevyAppWorkoutItem,
)
from fitness_tracker.database.repository.base import BaseRepository


class HevyAppWorkoutRepository(BaseRepository[HevyAppWorkout]):
    """Persistence access for :class:`~fitness_tracker.database.models.hevy_app.HevyAppWorkout`."""

    def __init__(self, session: Session) -> None:
        """Create a workout repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=HevyAppWorkout)


class HevyAppWorkoutItemRepository(BaseRepository[HevyAppWorkoutItem]):
    """Persistence access for Hevy :class:`HevyAppWorkoutItem` rows."""

    def __init__(self, session: Session) -> None:
        """Create a workout-item repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=HevyAppWorkoutItem)


class HevyAppSetsRepository(BaseRepository[HevyAppSets]):
    """Persistence access for :class:`~fitness_tracker.database.models.hevy_app.HevyAppSets`."""

    def __init__(self, session: Session) -> None:
        """Create a sets repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=HevyAppSets)


class HevyAppExerciseRepository(BaseRepository[HevyAppExercise]):
    """Persistence access for :class:`~fitness_tracker.database.models.hevy_app.HevyAppExercise`."""

    def __init__(self, session: Session) -> None:
        """Create an exercise repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=HevyAppExercise)


class HevyAppActivatedMuscleRepository(BaseRepository[HevyAppActivatedMuscle]):
    """Persistence access for Hevy :class:`HevyAppActivatedMuscle` rows."""

    def __init__(self, session: Session) -> None:
        """Create an activated-muscle repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=HevyAppActivatedMuscle)
