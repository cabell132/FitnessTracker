"""Adapter wrapping :class:`TrueCoachClient` behind :class:`TrueCoachAssessmentWriter`."""

from __future__ import annotations

from fitness_tracker.apis.true_coach.client import TrueCoachClient
from fitness_tracker.apis.true_coach.types import AssessmentItem, PostAssessmentItem


class TrueCoachAssessmentWriterAdapter:
    """Delegates assessment posts to the True Coach REST client."""

    def __init__(self, client: TrueCoachClient) -> None:
        """Wrap a True Coach client for assessment writes.

        Args:
            client (TrueCoachClient): True Coach API client.
        """
        self._client = client

    def post_assessment(self, assessment: PostAssessmentItem) -> AssessmentItem:
        """Create an assessment item via the True Coach API.

        Args:
            assessment (PostAssessmentItem): Request body wrapper.

        Returns:
            AssessmentItem: Persisted assessment from the response.
        """
        return self._client.assessments.post(assessment)
