"""True Coach exercises API resource."""

from fitness_tracker.apis.base import parse_response
from fitness_tracker.apis.session import APISession
from fitness_tracker.apis.true_coach.types import ExerciseResponse


class TrueCoachExercises:
    """Lists exercise definitions available to the client."""

    def __init__(self, session: APISession) -> None:
        """Attach this resource to an authenticated session.

        Args:
            session (APISession): Session used for HTTP calls.
        """
        self._session = session
        self.endpoint = "exercises"

    def get(self) -> ExerciseResponse | None:
        """Fetch all exercises exposed by the API.

        Returns:
            ExerciseResponse | None: Parsed list payload, or ``None`` when empty.
        """
        data = self._session.make_request(method="GET", endpoint=self.endpoint)
        return parse_response(data, ExerciseResponse)
