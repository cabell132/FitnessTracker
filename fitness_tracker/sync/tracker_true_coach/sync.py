"""Sync tracker metric rows to True Coach assessments."""

from fitness_tracker.apis import TrueCoachClient
from fitness_tracker.apis.true_coach.types import AssessmentItem, PostAssessment, PostAssessmentItem
from fitness_tracker.database import Store


class TrackerToTrueCoachSyncronizer:
    """Reads SQL-selected metric rows and posts them to True Coach."""

    def __init__(self, store: Store, target: TrueCoachClient) -> None:
        """Initiate the syncronizer with the clients.

        Args:
            store (Store): Persistence layer.
            target (TrueCoachClient): Client for assessment POSTs.
        """
        self._store = store
        self._target = target

    def sync_assessment(self, assessment_id: str, date: str, value: str) -> AssessmentItem:
        """Sync the assessment to True Coach.

        Args:
            assessment_id (str): The assessment id.
            date (str): The date of the assessment.
            value (str): The value of the assessment.

        Returns:
            AssessmentItem: The created assessment item from the API.
        """
        assessment = PostAssessmentItem(
            assessment_item=PostAssessment(
                assessment_id=assessment_id,
                date=date,
                created_at=date,
                value=value,
                attachments=[],
            )
        )
        return self._target.assessments.post(assessment)

    def sync_assessments(self) -> None:
        """Sync all the assessments."""
        with self._store.unit_of_work() as uow:
            rows = uow.cross_domain.select_tracker_tc_assessments()

            for row in rows:
                assessment_item = self.sync_assessment(
                    str(row["assessment_id"]),
                    str(row["date"]),
                    str(row["value"]),
                )
                uow.true_coach.add_assessment_item(assessment_item)
                uow.tracker.link_metric_item_to_true_coach(
                    metric_item_id=row["id"],
                    true_coach_id=assessment_item.id,
                )
