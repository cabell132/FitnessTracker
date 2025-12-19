
from fitness_tracker.apis.true_coach.session import TrueCoachSession
from fitness_tracker.apis.true_coach.types import ExerciseResponse
from typing import Optional

class TrueCoachExercises:
    """True Coach API Exercises class"""

    def __init__(self, session:TrueCoachSession) -> None:
        """Initiate the Exercises class with the token

        """
        self._session = session
        self.endpoint = "exercises"

    def get(self) -> Optional[ExerciseResponse]:
        """Get all the exercises"""
                
        data = self._session.make_request(method="GET", endpoint=self.endpoint)
        if data:
            return ExerciseResponse(**data)