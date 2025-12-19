from typing import Optional

from fitness_tracker.apis.true_coach.session import TrueCoachSession
from fitness_tracker.apis.true_coach.types import AssessmentResponse, PostAssessmentItem, AssessmentItem


class TrueCoachAssessments:
    """True Coach API Assessments class."""

    def __init__(self, session: TrueCoachSession) -> None:
        """Initiate the Assessments class with the token."""
        self._session = session
        self.endpoint = "assessments"

    def get(self, assessment_id: int) -> Optional[AssessmentResponse]:
        """Get all the exercises.

        Args:
            assessment_id (int): The assessment id.
        """
        response = self._session.make_request(
            method="GET", endpoint=self.endpoint + f"/{assessment_id}"
        )
        if response:
            return AssessmentResponse(**response)
        return None

    def get_weights(self) -> Optional[AssessmentResponse]:
        """Get all the exercises."""
        return self.get(assessment_id=13513325)

    def get_calories_burned(self) -> Optional[AssessmentResponse]:
        """Get all the exercises."""
        return self.get(assessment_id=14517944)

    def post(self, assessment_item: PostAssessmentItem) -> AssessmentItem:
        """Post an assessment item.

        Args:
            assessment_item (PostAssessmentItem): The assessment item.
        """
        response = self._session.make_request(
            method="POST", endpoint="/v2/assessment_items", json=assessment_item.model_dump()
        )
        return AssessmentItem(**response['assessment_item']) # type: ignore

