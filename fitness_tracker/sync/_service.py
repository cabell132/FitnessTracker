"""Intent-named service facade for all sync operations.

Callers use :class:`SyncService` instead of accessing directional syncers
directly.  The service hides which API endpoints are called, in what order,
and how cascades work (e.g. Hevy → Tracker triggers Hevy → True Coach).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fitness_tracker.apis.hevy_app.types import DeletedWorkout, Routine, UpdatedWorkout
from fitness_tracker.apis.true_coach.types import WorkoutResponse
from logs import WideEvent

from fitness_tracker.sync._deps import SyncDeps
from fitness_tracker.sync._run import SyncRunResult
from fitness_tracker.sync.adapters.file_checkpoint_store import HEVY_CHECKPOINT_KEY
from fitness_tracker.sync.adapters.hevy_routine_writer import HevyRoutineWriterAdapter
from fitness_tracker.sync.adapters.true_coach_workout_item_writer import (
    TrueCoachWorkoutItemWriterAdapter,
)
from fitness_tracker.sync.apple_health_tracker.sync import AppleHealthToFitnessTrackerSyncronizer
from fitness_tracker.sync.hevy_tracker.sync import HevyToFitnessTrackerSyncronizer
from fitness_tracker.sync.tracker_hevy.sync import TrackerToHevySyncronizer
from fitness_tracker.sync.tracker_true_coach.sync import TrackerToTrueCoachSyncronizer
from fitness_tracker.sync.true_coach_hevy.sync import TrueCoachToHevySyncronizer
from fitness_tracker.sync.true_coach_tracker.sync import TrueCoachToFitnessTrackerSyncronizer
from fitness_tracker.sync_review.hevy_to_true_coach_result_workflow import (
    HevyToTrueCoachResultSyncWorkflow,
)
from fitness_tracker.sync_review.true_coach_to_hevy import (
    RoutineReplacementBatchMutation,
    RoutineReplacementBatchResult,
    RoutineReplacementBatchWorkflow,
)

if TYPE_CHECKING:
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
            source=deps.true_coach,
            target=deps.hevy,
            llm=deps.llm,
        )
        self._hevy_to_tracker = HevyToFitnessTrackerSyncronizer(
            store=deps.store,
            source=deps.hevy,
            llm=deps.llm,
        )
        self._true_coach_workout_item_writer = TrueCoachWorkoutItemWriterAdapter(deps.true_coach)
        self._hevy_result_sync_workflow = HevyToTrueCoachResultSyncWorkflow(store=deps.store)
        self._routine_replacement_batch = RoutineReplacementBatchWorkflow(
            store=deps.store,
            output_root=deps.routine_review_output_root,
        )
        self._tc_to_tracker = TrueCoachToFitnessTrackerSyncronizer(
            store=deps.store,
            source=deps.true_coach,
        )
        self._tracker_to_hevy = TrackerToHevySyncronizer(
            store=deps.store,
            source=deps.true_coach,
            target=deps.hevy,
            llm=deps.llm,
        )
        self._ah_to_tracker = AppleHealthToFitnessTrackerSyncronizer(
            store=deps.store,
            source=deps.dbx,
        )
        self._tracker_to_tc = TrackerToTrueCoachSyncronizer(
            store=deps.store,
            target=deps.true_coach,
        )

    def _execute_full_sync(
        self,
        ts: datetime,
    ) -> tuple[list[UpdatedWorkout | DeletedWorkout], int, list[Any]]:
        """Run ordered platform steps and return counts inputs for :class:`SyncRunResult`.

        Args:
            ts (datetime): Wall time written to the Hevy checkpoint after Hevy sync.

        Returns:
            tuple[list[UpdatedWorkout | DeletedWorkout], int, list[Any]]: Hevy events, deleted Hevy
                routine count, due True Coach workouts (ORM rows).
        """
        checkpoints = self._deps.checkpoints
        self.sync_apple_health()

        res = self.fetch_recent_true_coach_workouts()
        if res is not None:
            self.sync_true_coach_workouts(res)

        hevy_default = datetime(2025, 1, 1, tzinfo=UTC)
        previous = checkpoints.read(HEVY_CHECKPOINT_KEY, hevy_default)
        events = self.sync_hevy_workouts(since=previous)
        checkpoints.write(HEVY_CHECKPOINT_KEY, ts)

        self.sync_assessments()
        res = self.fetch_recent_true_coach_workouts()
        if res is not None:
            self.sync_true_coach_workouts(res)

        workouts = self.get_due_workouts()
        routine_batch = self.replace_due_hevy_routines(workouts)

        return events, routine_batch.deleted_routine_count, workouts

    def run(self, *, now: datetime | None = None) -> SyncRunResult:
        """Execute the full sync pipeline with internal checkpoint lifecycle.

        Runs Apple Health import, Hevy incremental sync with checkpoints, assessments, routine
        cleanup, conditional True Coach import, and Hevy routine creation for due workouts.

        Args:
            now (datetime | None, optional): Wall clock override for tests.
                Defaults to ``datetime.now(tz=UTC)``.

        Returns:
            SyncRunResult: Counts, timing, and outcome summary.
        """
        ts = now if now is not None else datetime.now(tz=UTC)
        started = time.perf_counter()

        with WideEvent(operation="sync_run") as evt:
            events, deleted, workouts = self._execute_full_sync(ts)
            evt.set(
                hevy_event_count=len(events),
                hevy_routines_deleted=deleted,
                true_coach_workouts_synced=len(workouts),
            )

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        return SyncRunResult(
            hevy_event_count=len(events),
            hevy_routines_deleted=deleted,
            true_coach_workouts_synced=len(workouts),
            duration_ms=duration_ms,
            outcome="success",
        )

    def sync_apple_health(self) -> None:
        """Import Apple Health metrics and workouts from Dropbox."""
        self._ah_to_tracker.sync_metrics()
        self._ah_to_tracker.sync_workouts()

    def sync_hevy_workouts(self, since: datetime) -> list[UpdatedWorkout | DeletedWorkout]:
        """Fetch Hevy events, update tracker, and cascade to True Coach.

        Args:
            since (datetime): Lower bound for the Hevy events query.

        Returns:
            list[UpdatedWorkout | DeletedWorkout]: Events applied (oldest first).
        """
        events = self._hevy_to_tracker.sync_workouts(since=since)

        for event in events:
            if isinstance(event, UpdatedWorkout):
                self._hevy_result_sync_workflow.sync_one(
                    event.workout.id,
                    workout_item_writer=self._true_coach_workout_item_writer,
                )

        return events

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

    def replace_due_hevy_routines(
        self,
        workouts: list[TrueCoachWorkout],
    ) -> RoutineReplacementBatchResult:
        """Review-gate a batch of due Routine replacements before mutating Hevy.

        Args:
            workouts (list[TrueCoachWorkout]): Due True Coach workouts to create as Hevy Routines.

        Returns:
            RoutineReplacementBatchResult: Batch status, artifacts, and mutation count.
        """
        return self._routine_replacement_batch.sync(
            workouts,
            mutation=RoutineReplacementBatchMutation(
                routine_writer=HevyRoutineWriterAdapter(self._deps.hevy),
                list_existing_routines=self.list_hevy_routines,
                delete_routine=self.delete_hevy_routine,
            ),
        )

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
        routines = self._deps.hevy.routines.get(page=page, per_page=per_page)
        if routines is None:
            return 0
        for routine in routines.routines:
            self._deps.hevy.routines.delete(routine.id)
        return len(routines.routines)

    def list_hevy_routines(self, per_page: int = 10) -> list[Routine]:
        """Fetch all visible Hevy routine drafts.

        Args:
            per_page (int): Page size.

        Returns:
            list[Routine]: Routines returned by the Hevy API.
        """
        routines: list[Routine] = []
        page = 1
        while True:
            response = self._deps.hevy.routines.get(page=page, per_page=per_page)
            if response is None:
                return routines
            routines.extend(response.routines)
            if page >= response.page_count:
                return routines
            page += 1

    def delete_hevy_routine(self, routine_id: str) -> None:
        """Delete one Hevy routine draft by id.

        Args:
            routine_id (str): Hevy Routine id to delete.
        """
        self._deps.hevy.routines.delete(routine_id)

    def fetch_recent_true_coach_workouts(self) -> WorkoutResponse | None:
        """Fetch recent True Coach workouts for sync.

        Returns:
            WorkoutResponse | None: API response or ``None`` when empty.
        """
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
            return uow.true_coach.get_workouts(due=due)
