"""Port for posting assessment measurements to True Coach."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fitness_tracker.apis.true_coach.types import AssessmentItem, PostAssessmentItem


@runtime_checkable
class TrueCoachAssessmentWriter(Protocol):
    """Post assessment measurements to True Coach."""

    def post_assessment(self, assessment: PostAssessmentItem) -> AssessmentItem:
        """Create an assessment item row via the True Coach API.

        Args:
            assessment (PostAssessmentItem): Request body wrapper for the assessment measurement.

        Returns:
            AssessmentItem: Persisted assessment item parsed from the response.
        """
        ...
