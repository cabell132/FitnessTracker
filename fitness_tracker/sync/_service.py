"""Intent-named service facade for all sync operations.

Callers use :class:`SyncService` instead of accessing directional syncers
directly.  The service hides which API endpoints are called, in what order,
and how cascades work (e.g. Hevy -> Tracker triggers Hevy -> True Coach).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fitness_tracker.apis.true_coach.types import WorkoutResponse
from fitness_tracker.sync._deps import SyncDeps
from fitness_tracker.sync.apple_health_tracker.sync import AppleHealthToFitnessTrackerSyncronizer
from fitness_tracker.sync.domain.events import SyncEvent, WorkoutDeleted, WorkoutSynced
from fitness_tracker.sync.hevy_tracker.sync import HevyToFitnessTrackerSyncronizer
from fitness_tracker.sync.hevy_true_coach.sync import HevyToTrueCoachSyncronizer
from fitness_tracker.sync.tracker_hevy.sync import TrackerToHevySyncronizer
from fitness_tracker.sync.tracker_true_coach.sync import TrackerToTrueCoachSyncronizer
from fitness_tracker.sync.true_coach_hevy.sync import TrueCoachToHevySyncronizer
from fitness_tracker.sync.true_coach_tracker.sync import TrueCoachToFitnessTrackerSyncronizer

if TYPE_CHECKING:
    from fitness_tracker.apis.hevy_app.types import DeletedWorkout, UpdatedWorkout
    from fitness_tracker.database.models.true_coach import TrueCoachWorkout


class SyncService:
    """Intent-named methods replace direction-named attributes.

    Each public method maps to a business-level sync operation.  The
    internal syncer wiring, cascade ordering, and checkpoint management
    are implementation details hidden from callers.
    """

    def __init__(self, deps: SyncDeps) -> None:
        """Wire internal syncers from a dependency bundle.

        Args:
            deps (SyncDeps): All external dependencies needed by the service.
        """
        self._deps = deps
        self._store = deps.store

        # --- internal syncers (callers never see these) ---
        self._tc_to_hevy = TrueCoachToHevySyncronizer(
            store=deps.store,
            routine_writer=deps.hevy_routine_writer,
            set_parser=deps.set_parser,
        )
        self._hevy_to_tracker = HevyToFitnessTrackerSyncronizer(
            store=deps.store,
            event_source=deps.hevy_event_source,
            item_linker=deps.item_linker,
            template_lookup=deps.hevy_template_lookup,
        )
        self._hevy_to_tc = HevyToTrueCoachSyncronizer(
            store=deps.store,
            tc_item_writer=deps.tc_item_writer,
        )
        self._tc_to_tracker = TrueCoachToFitnessTrackerSyncronizer(
            store=deps.store,
        )
        self._tracker_to_hevy = TrackerToHevySyncronizer(
            store=deps.store,
            workout_writer=deps.hevy_workout_writer,
            set_parser=deps.set_parser,
        )
        self._ah_to_tracker = AppleHealthToFitnessTrackerSyncronizer(
            store=deps.store,
            health_export=deps.health_export,
        )
        self._tracker_to_tc = TrackerToTrueCoachSyncronizer(
            store=deps.store,
            assessment_writer=deps.tc_assessment_writer,
        )

    def sync_apple_health(self) -> None:
        """Import Apple Health metrics and workouts from remote storage."""
        self._ah_to_tracker.sync_metrics()
        self._ah_to_tracker.sync_workouts()

    def sync_hevy_workouts(self, since: datetime) -> list[SyncEvent]:
        """Fetch Hevy events, update tracker, and cascade to True Coach.

        Args:
            since (datetime): Lower bound for the Hevy events query.

        Returns:
            list[SyncEvent]: Domain events representing what happened (oldest first).
        """
        from fitness_tracker.apis.hevy_app.types import UpdatedWorkout  # noqa: PLC0415

        raw_events = self._hevy_to_tracker.sync_workouts(since=since)

        with self._store.unit_of_work():
            for event in raw_events:
                if isinstance(event, UpdatedWorkout):
                    self._hevy_to_tc.sync_workout(event.workout.id)

        return self._to_domain_events(raw_events)

    @staticmethod
    def _to_domain_events(
        raw_events: list[UpdatedWorkout | DeletedWorkout],
    ) -> list[SyncEvent]:
        """Map API DTOs to sync-layer domain events.

        Args:
            raw_events (list[UpdatedWorkout | DeletedWorkout]): Raw API events.

        Returns:
            list[SyncEvent]: Domain-typed events.
        """
        from fitness_tracker.apis.hevy_app.types import (  # noqa: PLC0415
            DeletedWorkout,
            UpdatedWorkout,
        )
        from fitness_tracker.sync.hevy_tracker.sync import (  # noqa: PLC0415
            _parse_api_datetime,
        )

        domain_events: list[SyncEvent] = []
        for event in raw_events:
            if isinstance(event, UpdatedWorkout):
                wo = event.workout
                domain_events.append(
                    WorkoutSynced(
                        hevy_workout_id=wo.id,
                        title=wo.title,
                        started_at=_parse_api_datetime(wo.start_time),
                        ended_at=_parse_api_datetime(wo.end_time),
                    )
                )
            elif isinstance(event, DeletedWorkout):
                domain_events.append(
                    WorkoutDeleted(
                        hevy_workout_id=event.id,
                        deleted_at=datetime.now(tz=UTC),
                    )
                )
        return domain_events

    def sync_true_coach_workouts(self, workouts: WorkoutResponse) -> None:
        """Persist True Coach workout snapshots into the tracker.

        Args:
            workouts (WorkoutResponse): API response containing workouts and items.
        """
        self._tc_to_tracker.sync_workouts(workouts)

    def create_hevy_routine(self, workout_id: int) -> None:
        """Build a Hevy routine draft from a True Coach workout.

        Args:
            workout_id (int): True Coach workout id to convert.
        """
        self._tc_to_hevy.sync_workout(workout_id)

    def sync_assessments(self) -> None:
        """Push tracker metric rows to True Coach assessments."""
        self._tracker_to_tc.sync_assessments()

    def post_hevy_workout(self, workout_id: int) -> None:
        """Post a completed workout to Hevy from tracker state.

        Args:
            workout_id (int): True Coach workout id backing the tracker workout.
        """
        self._tracker_to_hevy.sync_workout(workout_id)

    def clear_hevy_routines(self, page: int = 1, per_page: int = 10) -> int:
        """Delete existing Hevy routine drafts.

        Args:
            page (int): Page of routines to fetch for deletion.
            per_page (int): Number of routines per page.

        Returns:
            int: Number of routines deleted.
        """
        if self._deps.hevy is None:
            return 0
        routines = self._deps.hevy.routines.get(page=page, per_page=per_page)
        if routines is None:
            return 0
        for routine in routines.routines:
            self._deps.hevy.routines.delete(routine.id)
        return len(routines.routines)

    def fetch_recent_true_coach_workouts(self) -> WorkoutResponse | None:
        """Fetch recent True Coach workouts for sync.

        Returns:
            WorkoutResponse | None: API response or ``None`` when empty.
        """
        if self._deps.true_coach is None:
            return None
        return self._deps.true_coach.workouts.get(
            order="desc",
            page=1,
            per_page=10,
            states=["pending", "completed", "missed"],
        )

    def get_due_workouts(self) -> list[TrueCoachWorkout]:
        """Return True Coach workouts due today.

        Returns:
            list[TrueCoachWorkout]: Workouts due on or before today's midnight UTC.
        """
        with self._store.unit_of_work() as uow:
            due = datetime.now(tz=UTC).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            return uow.tc_get_workouts(due=due)
