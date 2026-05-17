"""Hevy App exercise template endpoints."""

from fitness_tracker.apis.base import parse_response
from fitness_tracker.apis.session import APISession
from fitness_tracker.apis.hevy_app.types import (
    CreateCustomExerciseRequestBody,
    CreateCustomExerciseResponse,
    ExerciseResponse,
    ExerciseTemplate,
)


class HevyAppExercises:
    """Lists and creates exercise templates via the REST API."""

    def __init__(self, session: APISession, web_session: APISession) -> None:
        """Attach HTTP sessions (web session reserved for future use).

        Args:
            session (APISession): Authenticated JSON API session.
            web_session (APISession): Web-token session for future endpoints.
        """
        self._session = session
        self.endpoint = "/exercise_templates"
        self._web_session = web_session

    def get(self, page: int = 1, per_page: int = 10) -> ExerciseResponse | None:
        """List exercise templates with pagination.

        Args:
            page (int): Page index (1-based).
            per_page (int): Page size (max 100 per Hevy docs).

        Returns:
            ExerciseResponse | None: Parsed page, or ``None`` when the body is empty.
        """
        query = {"page": page, "pageSize": per_page}
        data = self._session.make_request(method="GET", endpoint=self.endpoint, params=query)
        return parse_response(data, ExerciseResponse)

    def get_template(self, template_id: str) -> ExerciseTemplate | None:
        """Fetch a single exercise template by id.

        Args:
            template_id (str): Exercise template id.

        Returns:
            ExerciseTemplate | None: Template when found; ``None`` if absent.
        """
        endpoint = f"{self.endpoint}/{template_id}"
        data = self._session.make_request(method="GET", endpoint=endpoint)
        return parse_response(data, ExerciseTemplate)

    def create(
        self, exercise: CreateCustomExerciseRequestBody
    ) -> CreateCustomExerciseResponse | None:
        """Create a new custom exercise template.

        Args:
            exercise (CreateCustomExerciseRequestBody): Wrapper accepted by the API.

        Returns:
            CreateCustomExerciseResponse | None: Created template id, or ``None`` when empty.
        """
        data = self._session.make_request(
            method="POST", endpoint=self.endpoint, json=exercise.model_dump()
        )
        return parse_response(data, CreateCustomExerciseResponse)
