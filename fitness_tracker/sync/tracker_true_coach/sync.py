from pathlib import Path

from fitness_tracker.apis import TrueCoachClient
from fitness_tracker.apis.true_coach.types import AssessmentItem, PostAssessment, PostAssessmentItem
from fitness_tracker.database import Database
from sqlalchemy import text


class TrackerToTrueCoachSyncronizer:
    """Syncronizer class"""

    def __init__(self, database: Database, target: TrueCoachClient) -> None:
        """Initiate the syncronizer with the clients."""
        self._database = database
        self._target = target

    def sync_assessment(self, assessment_id: str, date: str, value: str) -> AssessmentItem:
        """Sync the assessment to True Coach.

        Args:
            assessment_id (str): The assessment id.
            date (str): The date of the assessment.
            value (str): The value of the assessment.
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
        query = text(
            Path(
                "fitness_tracker/database/SQL/tracker/true_coach/assessments/select.sql"
            ).read_text()
        )

        with self._database.tracker.get_session() as session:
            result = session.execute(query)  # type: ignore
            result = result.fetchall()

        with self._database.true_coach.get_session() as session:
            for row in result:  # type: ignore
                assessment_item = self.sync_assessment(
                    str(row["assessment_id"]),  # type: ignore
                    str(row["date"]),  # type: ignore
                    str(row["value"]),  # type: ignore
                )
                self._database.true_coach.add_assessment_item(session, assessment_item)
                update_query = text("""
                UPDATE MetricItem
                SET true_coach_id = :true_coach_id
                WHERE id = :id
                """)
                session.execute(  # type: ignore
                    update_query,
                    {"true_coach_id": assessment_item.id, "id": row["id"]},  # type: ignore
                )
                session.commit()
