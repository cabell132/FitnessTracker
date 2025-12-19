from fitness_tracker.apis.hevy_app.session import HevyAppSession
from fitness_tracker.apis.hevy_app.web_session import HevyAppWebSession
from fitness_tracker.apis.hevy_app.exercises import HevyAppExercises
from fitness_tracker.apis.hevy_app.workouts import HevyAppWorkouts
from fitness_tracker.apis.hevy_app.routines import HevyAppRoutines
from fitness_tracker.apis.base import BaseClient


class HevyAppClient(BaseClient):
    """Hevy App API client class"""

    def __init__(self) -> None:
        """Initiate the client with the token"""
        self._session = HevyAppSession()
        self._web_session = HevyAppWebSession()
        self.exercises = HevyAppExercises(session=self._session, web_session=self._web_session)
        self.workouts = HevyAppWorkouts(session=self._session)
        self.routines = HevyAppRoutines(session=self._session, web_session=self._web_session)
