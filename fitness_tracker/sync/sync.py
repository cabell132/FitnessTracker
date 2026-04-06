"""Legacy orchestrator — prefer :class:`SyncService` for new code.

Retained for backwards compatibility with any call sites that reference
the ``Syncronizer`` class directly.
"""

from __future__ import annotations

from fitness_tracker.sync._deps import SyncDeps
from fitness_tracker.sync.apple_health_tracker.sync import AppleHealthToFitnessTrackerSyncronizer
from fitness_tracker.sync.hevy_tracker.sync import HevyToFitnessTrackerSyncronizer
from fitness_tracker.sync.hevy_true_coach.sync import HevyToTrueCoachSyncronizer
from fitness_tracker.sync.tracker_hevy.sync import TrackerToHevySyncronizer
from fitness_tracker.sync.tracker_true_coach.sync import TrackerToTrueCoachSyncronizer
from fitness_tracker.sync.true_coach_hevy.sync import TrueCoachToHevySyncronizer
from fitness_tracker.sync.true_coach_tracker.sync import TrueCoachToFitnessTrackerSyncronizer

from sqlalchemy.engine import Engine


class Syncronizer:
    """Orchestrator that wires database and API clients to directional syncers.

    .. deprecated::
        Use :class:`SyncService` with :class:`SyncDeps` instead.
    """

    def __init__(self, engine: Engine) -> None:
        """Wire API clients, Dropbox, and directional syncers to one engine.

        Args:
            engine (Engine): SQLAlchemy engine backing :class:`~fitness_tracker.database.Store`.
        """
        deps = SyncDeps.from_engine(engine)

        self.true_coach_to_hevy = TrueCoachToHevySyncronizer(
            store=deps.store,
            routine_writer=deps.hevy_routine_writer,
            set_parser=deps.set_parser,
        )
        self.hevy_to_tracker = HevyToFitnessTrackerSyncronizer(
            store=deps.store,
            event_source=deps.hevy_event_source,
            item_linker=deps.item_linker,
            template_lookup=deps.hevy_template_lookup,
        )
        self.hevy_to_true_coach = HevyToTrueCoachSyncronizer(
            store=deps.store,
            tc_item_writer=deps.tc_item_writer,
        )
        self.true_coach_to_tracker = TrueCoachToFitnessTrackerSyncronizer(
            store=deps.store,
        )
        self.tracker_to_hevy = TrackerToHevySyncronizer(
            store=deps.store,
            workout_writer=deps.hevy_workout_writer,
            set_parser=deps.set_parser,
        )
        self.apple_health_to_tracker = AppleHealthToFitnessTrackerSyncronizer(
            store=deps.store,
            health_export=deps.health_export,
        )
        self.tracker_to_true_coach = TrackerToTrueCoachSyncronizer(
            store=deps.store,
            assessment_writer=deps.tc_assessment_writer,
        )
