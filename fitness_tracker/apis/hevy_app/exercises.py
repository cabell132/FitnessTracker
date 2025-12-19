from typing import Optional

from fitness_tracker.apis.hevy_app.session import HevyAppSession
from fitness_tracker.apis.hevy_app.web_session import HevyAppWebSession
from fitness_tracker.apis.hevy_app.types import ExerciseResponse, ExerciseTemplate
from fitness_tracker.llm.fitness_llm import FitnessLLM


class HevyAppExercises:
    """True Coach API Exercises class."""

    def __init__(self, session: HevyAppSession, web_session: HevyAppWebSession) -> None:
        """Initiate the Exercises class with the token."""
        self._session = session
        self.endpoint = "/exercise_templates"
        self._web_session = web_session

    def get(self, page: int = 1, per_page: int = 10) -> Optional[ExerciseResponse]:
        """Get a paginated list of exercise templates available on the account.

        Args:
            page (int): The page number to retrieve. Defaults to 1. Minimum is 1.
            per_page (int): The number of items per page. Defaults to 10. Maximum is 100.
        """
        query = {"page": page, "pageSize": per_page}

        data = self._session.make_request(method="GET", endpoint=self.endpoint, params=query)
        if data:
            return ExerciseResponse(**data)
        return None

    def get_template(self, id: str) -> Optional[ExerciseTemplate]:
        """Get a single exercise template by ID.

        Args:
            id (int): The ID of the exercise template to retrieve.
        """
        endpoint = f"{self.endpoint}/{id}"
        data = self._session.make_request(method="GET", endpoint=endpoint)
        if data:
            return ExerciseTemplate(**data)
        return None
