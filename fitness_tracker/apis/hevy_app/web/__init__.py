"""Private Hevy website API, exposed through HevyAppClient.web."""

from __future__ import annotations

from fitness_tracker.apis.hevy_app.web._resource import WebSession
from fitness_tracker.apis.hevy_app.web.account import WebPreferences, WebUsers, WebWebhooks
from fitness_tracker.apis.hevy_app.web.exercises import WebExercises
from fitness_tracker.apis.hevy_app.web.models import (
    WebExercise,
    WebExerciseTemplate,
    WebFolder,
    WebRecord,
    WebRoutine,
    WebSet,
    WebWorkout,
)
from fitness_tracker.apis.hevy_app.web.routines import WebFolders, WebRoutines
from fitness_tracker.apis.hevy_app.web.workouts import WebWorkouts

__all__ = [
    "HevyWebClient",
    "WebExercise",
    "WebExerciseTemplate",
    "WebFolder",
    "WebRecord",
    "WebRoutine",
    "WebSet",
    "WebWorkout",
]


class HevyWebClient:
    """Cohesive web resources sharing one rotating authentication session."""

    def __init__(self, session: WebSession) -> None:
        """Attach website resources to an existing authenticated session.

        Args:
            session (WebSession): Shared refreshing web request boundary.
        """
        self.workouts = WebWorkouts(session)
        self.routines = WebRoutines(session)
        self.exercises = WebExercises(session)
        self.folders = WebFolders(session)
        self.users = WebUsers(session)
        self.preferences = WebPreferences(session)
        self.webhooks = WebWebhooks(session)
