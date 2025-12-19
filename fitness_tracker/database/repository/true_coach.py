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
    """True Coach repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session."""
        super().__init__(session=session, model_class=TrueCoachExercise)


class TrueCoachWorkoutRepository(BaseRepository[TrueCoachWorkout]):
    """True Coach repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session."""
        super().__init__(session=session, model_class=TrueCoachWorkout)


class TrueCoachTagRepository(BaseRepository[TrueCoachTag]):
    """True Coach repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session."""
        super().__init__(session=session, model_class=TrueCoachTag)


class TrueCoachWorkoutItemRepository(BaseRepository[TrueCoachWorkoutItem]):
    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session."""
        super().__init__(session=session, model_class=TrueCoachWorkoutItem)


class TrueCoachExerciseTagsRepository(BaseRepository[TrueCoachExerciseTags]):
    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session."""
        super().__init__(session=session, model_class=TrueCoachExerciseTags)


class TrueCoachAssessmentRepository(BaseRepository[TrueCoachAssessment]):
    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session."""
        super().__init__(session=session, model_class=TrueCoachAssessment)


class TrueCoachAssessmentItemRepository(BaseRepository[TrueCoachAssessmentItem]):
    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session."""
        super().__init__(session=session, model_class=TrueCoachAssessmentItem)
