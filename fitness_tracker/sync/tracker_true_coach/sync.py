"""Sync tracker metric rows to True Coach assessments."""

from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fitness_tracker.apis import TrueCoachClient
from fitness_tracker.apis.true_coach.types import AssessmentItem, PostAssessment, PostAssessmentItem
from fitness_tracker.database import Store
from fitness_tracker.database.models.vesync import VeSyncWeighIn

_WEIGHT_ASSESSMENT_ID = 13513325
_WEIGHT_MATCH_TOLERANCE_KG = Decimal("0.02")
_LOCAL_ZONE = ZoneInfo("Europe/London")


def _local_day(timestamp: datetime) -> date:
    """Use the athlete's calendar day for True Coach chart comparisons.

    Args:
        timestamp (datetime): Measurement time in UTC.

    Returns:
        date: Calendar date in London.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(_LOCAL_ZONE).date()


def _weight_history_by_day(items: list[AssessmentItem]) -> dict[date, list[Decimal]]:
    existing: dict[date, list[Decimal]] = defaultdict(list)
    for item in items:
        existing[_local_day(datetime.fromisoformat(item.date))].append(Decimal(item.value))
    return existing


def _utc_timestamp(timestamp: datetime) -> str:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


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
        self.sync_vesync_weights()

    def sync_vesync_weights(self) -> int:
        """Post scale readings missing from the True Coach weight chart.

        Returns:
            int: Number of readings posted.

        Raises:
            ValueError: If the configured assessment is missing or has unexpected units.
        """
        response = self._target.assessments.get_weights()
        if (
            response is None
            or response.assessment.id != _WEIGHT_ASSESSMENT_ID
            or response.assessment.units.lower() != "kilograms"
        ):
            msg = "True Coach weight assessment is unavailable or has unexpected units"
            raise ValueError(msg)

        existing = _weight_history_by_day(response.assessment_items)

        with self._store.unit_of_work() as uow:
            uow.true_coach.add_assessment(response)

        rows = sorted(self._store.query_all(VeSyncWeighIn), key=lambda row: row.measured_at)
        posted_count = 0
        for row in rows:
            day = _local_day(row.measured_at)
            weight_kg = Decimal(row.weight_g) / 1000
            if any(
                abs(weight_kg - current) <= _WEIGHT_MATCH_TOLERANCE_KG for current in existing[day]
            ):
                continue

            timestamp = _utc_timestamp(row.measured_at)
            item = self.sync_assessment(str(_WEIGHT_ASSESSMENT_ID), timestamp, f"{weight_kg:.2f}")
            with self._store.unit_of_work() as uow:
                uow.true_coach.add_assessment_item(item)
            existing[day].append(weight_kg)
            posted_count += 1
        return posted_count
