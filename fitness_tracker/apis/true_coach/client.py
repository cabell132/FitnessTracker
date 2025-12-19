from fitness_tracker.apis.true_coach.session import TrueCoachSession
from fitness_tracker.apis.true_coach.workouts import TrueCoachWorkouts
from fitness_tracker.apis.true_coach.exercises import TrueCoachExercises
from fitness_tracker.apis.true_coach.assessments import TrueCoachAssessments
from fitness_tracker.apis.base import BaseClient

class TrueCoachClient(BaseClient):
    """True Coach API client class"""
    
    def __init__(self) -> None:
        """Initiate the client with the token

        """
        self._session = TrueCoachSession()
        self.workouts = TrueCoachWorkouts(session=self._session)
        self.exercises = TrueCoachExercises(session=self._session)
        self.assessments = TrueCoachAssessments(session=self._session)
