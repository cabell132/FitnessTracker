"""Hevy App API client entrypoint."""

from fitness_tracker.apis.base import BaseClient
from fitness_tracker.apis.hevy_app.exercise_history import HevyAppExerciseHistory
from fitness_tracker.apis.hevy_app.exercises import HevyAppExercises
from fitness_tracker.apis.hevy_app.routine_folders import HevyAppRoutineFolders
from fitness_tracker.apis.hevy_app.routines import HevyAppRoutines
from fitness_tracker.apis.hevy_app.session import HevyAppSession
from fitness_tracker.apis.hevy_app.users import HevyAppUsers
from fitness_tracker.apis.hevy_app.web_session import HevyAppWebSession
from fitness_tracker.apis.hevy_app.workouts import HevyAppWorkouts


class HevyAppClient(BaseClient):
    """Composes REST and web sessions with all Hevy API resources."""

    def __init__(self) -> None:
        """Create sub-resources with shared API sessions."""
        self._session = HevyAppSession()
        self._web_session = HevyAppWebSession()
        self.users = HevyAppUsers(session=self._session)
        self.exercises = HevyAppExercises(session=self._session, web_session=self._web_session)
        self.exercise_history = HevyAppExerciseHistory(session=self._session)
        self.workouts = HevyAppWorkouts(session=self._session)
        self.routines = HevyAppRoutines(session=self._session, web_session=self._web_session)
        self.routine_folders = HevyAppRoutineFolders(session=self._session)
