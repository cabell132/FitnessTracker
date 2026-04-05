"""Repositories for True Coach ORM tables."""

from sqlalchemy.orm import Session

from fitness_tracker.database.models.true_coach import (
    TrueCoachAssessment,
    TrueCoachAssessmentItem,
    TrueCoachExercise,
    TrueCoachExerciseTags,
    TrueCoachTag,
    TrueCoachWorkout,
    TrueCoachWorkoutItem,
)
from fitness_tracker.database.repository.base import BaseRepository


class TrueCoachExerciseRepository(BaseRepository[TrueCoachExercise]):
    """Persistence access for :class:`TrueCoachExercise` rows."""

    def __init__(self, session: Session) -> None:
        """Create an exercise repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=TrueCoachExercise)


class TrueCoachWorkoutRepository(BaseRepository[TrueCoachWorkout]):
    """Persistence access for :class:`TrueCoachWorkout` rows."""

    def __init__(self, session: Session) -> None:
        """Create a workout repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=TrueCoachWorkout)


class TrueCoachTagRepository(BaseRepository[TrueCoachTag]):
    """Persistence access for :class:`TrueCoachTag` rows."""

    def __init__(self, session: Session) -> None:
        """Create a tag repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=TrueCoachTag)


class TrueCoachWorkoutItemRepository(BaseRepository[TrueCoachWorkoutItem]):
    """Persistence access for :class:`TrueCoachWorkoutItem` rows."""

    def __init__(self, session: Session) -> None:
        """Create a workout-item repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=TrueCoachWorkoutItem)


class TrueCoachExerciseTagsRepository(BaseRepository[TrueCoachExerciseTags]):
    """Persistence access for :class:`TrueCoachExerciseTags` association rows."""

    def __init__(self, session: Session) -> None:
        """Create an exercise-tags repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=TrueCoachExerciseTags)


class TrueCoachAssessmentRepository(BaseRepository[TrueCoachAssessment]):
    """Persistence access for :class:`TrueCoachAssessment` rows."""

    def __init__(self, session: Session) -> None:
        """Create an assessment repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=TrueCoachAssessment)


class TrueCoachAssessmentItemRepository(BaseRepository[TrueCoachAssessmentItem]):
    """Persistence access for :class:`TrueCoachAssessmentItem` rows."""

    def __init__(self, session: Session) -> None:
        """Create an assessment-item repository for the given session.

        Args:
            session (Session): Active SQLAlchemy session.
        """
        super().__init__(session=session, model_class=TrueCoachAssessmentItem)
