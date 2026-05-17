"""High-level True Coach API client."""

from fitness_tracker.apis.base import BaseClient
from fitness_tracker.apis.true_coach.assessments import TrueCoachAssessments
from fitness_tracker.apis.true_coach.exercises import TrueCoachExercises
from fitness_tracker.apis.true_coach.session import true_coach_session
from fitness_tracker.apis.true_coach.workouts import TrueCoachWorkouts


class TrueCoachClient(BaseClient):
    """Bundles session, workouts, exercises, and assessments APIs."""

    def __init__(self, *, email: str, password: str) -> None:
        """Create a client with a default authenticated session.

        Args:
            email (str): True Coach login email.
            password (str): True Coach password.
        """
        self._session = true_coach_session(email=email, password=password)
        self.workouts = TrueCoachWorkouts(session=self._session)
        self.exercises = TrueCoachExercises(session=self._session)
        self.assessments = TrueCoachAssessments(session=self._session)
