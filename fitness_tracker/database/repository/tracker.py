from sqlalchemy.orm import Session

from fitness_tracker.database.models.tracker import Exercise, Sets, Workout, WorkoutItem
from fitness_tracker.database.repository.base import BaseRepository


class FitnessTrackerWorkoutRepository(BaseRepository[Workout]):
    """True Coach repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session.

        Args:
            session (Session): The session to use
        """
        super().__init__(session=session, model_class=Workout)


class FitnessTrackerExerciseRepository(BaseRepository[Exercise]):
    """True Coach repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session.

        Args:
            session (Session): The session to use

        """
        super().__init__(session=session, model_class=Exercise)


class FitnessTrackerWorkoutItemRepository(BaseRepository[WorkoutItem]):
    """True Coach repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session.

        Args:
            session (Session): The session to use

        """
        super().__init__(session=session, model_class=WorkoutItem)


class FitnessTrackerSetsRepository(BaseRepository[Sets]):
    """True Coach repository class."""

    def __init__(self, session: Session) -> None:
        """Initiate the True Coach repository with the session.

        Args:
            session (Session): The session to use

        """
        super().__init__(session=session, model_class=Sets)
