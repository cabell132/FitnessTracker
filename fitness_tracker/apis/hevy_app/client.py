"""Hevy App API client entrypoint."""

from pathlib import Path

from fitness_tracker.apis.base import BaseClient
from fitness_tracker.apis.hevy_app.exercise_history import HevyAppExerciseHistory
from fitness_tracker.apis.hevy_app.exercises import HevyAppExercises
from fitness_tracker.apis.hevy_app.routine_folders import HevyAppRoutineFolders
from fitness_tracker.apis.hevy_app.routines import HevyAppRoutines
from fitness_tracker.apis.hevy_app.session import hevy_session
from fitness_tracker.apis.hevy_app.users import HevyAppUsers
from fitness_tracker.apis.hevy_app.web import HevyWebClient
from fitness_tracker.apis.hevy_app.web_session import hevy_web_session
from fitness_tracker.apis.hevy_app.web_auth import default_hevy_web_credentials_path
from fitness_tracker.apis.hevy_app.workouts import HevyAppWorkouts


class HevyAppClient(BaseClient):
    """Composes REST and web sessions with all Hevy API resources."""

    def __init__(
        self,
        *,
        api_key: str,
        web_api_key: str,
        web_credentials_path: Path | None = None,
    ) -> None:
        """Create sub-resources with shared API sessions.

        Args:
            api_key (str): Hevy REST API key.
            web_api_key (str): Legacy web token from the ``HEVY_WEB_API_KEY`` env alias.
            web_credentials_path (Path | None): Rotating web credential store path.
        """
        self._session = hevy_session(api_key)
        legacy_web_access_token = web_api_key
        self._web_session = hevy_web_session(
            legacy_web_access_token,
            credentials_path=web_credentials_path or default_hevy_web_credentials_path(),
        )
        self.web = HevyWebClient(self._web_session)
        self.users = HevyAppUsers(session=self._session)
        self.exercises = HevyAppExercises(session=self._session, web_session=self._web_session)
        self.exercise_history = HevyAppExerciseHistory(session=self._session)
        self.workouts = HevyAppWorkouts(session=self._session)
        self.routines = HevyAppRoutines(session=self._session, web_session=self._web_session)
        self.routine_folders = HevyAppRoutineFolders(session=self._session)
