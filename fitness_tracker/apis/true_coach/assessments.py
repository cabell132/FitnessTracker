"""True Coach assessments API resource."""

from fitness_tracker.apis.session import APISession
from fitness_tracker.apis.true_coach.types import (
    AssessmentItem,
    AssessmentResponse,
    PostAssessmentItem,
)


class TrueCoachAssessments:
    """Fetches and posts client assessment data."""

    def __init__(self, session: APISession) -> None:
        """Attach this resource to an authenticated session.

        Args:
            session (APISession): Session used for HTTP calls.
        """
        self._session = session
        self.endpoint = "assessments"

    def get(self, assessment_id: int) -> AssessmentResponse | None:
        """Load one assessment and its items.

        Args:
            assessment_id (int): True Coach assessment id.

        Returns:
            AssessmentResponse | None: Parsed payload, or ``None`` if the body was empty.
        """
        response = self._session.make_request(
            method="GET", endpoint=self.endpoint + f"/{assessment_id}"
        )
        if response:
            return AssessmentResponse(**response)
        return None

    def get_weights(self) -> AssessmentResponse | None:
        """Load the configured body-weight assessment.

        Returns:
            AssessmentResponse | None: Assessment payload when available.
        """
        return self.get(assessment_id=13513325)

    def get_calories_burned(self) -> AssessmentResponse | None:
        """Load the configured calories-burned assessment.

        Returns:
            AssessmentResponse | None: Assessment payload when available.
        """
        return self.get(assessment_id=14517944)

    def post(self, assessment_item: PostAssessmentItem) -> AssessmentItem:
        """Create an assessment item row via the API.

        Args:
            assessment_item (PostAssessmentItem): Request body wrapper.

        Returns:
            AssessmentItem: Persisted item parsed from the response.

        Raises:
            ValueError: If the API returns an empty body.
        """
        response = self._session.make_request(
            method="POST",
            endpoint="/v2/assessment_items",
            json=assessment_item.model_dump(),
        )
        if response is None:
            msg = "Unexpected empty response from assessment_items POST"
            raise ValueError(msg)
        return AssessmentItem(**response["assessment_item"])
