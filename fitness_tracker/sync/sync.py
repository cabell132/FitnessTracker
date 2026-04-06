"""Composes directional sync classes for Hevy, True Coach, and Apple Health."""

import os

import dropbox
from sqlalchemy.engine import Engine

from fitness_tracker.apis import HevyAppClient, TrueCoachClient
from fitness_tracker.database import Store
from fitness_tracker.llm.fitness_llm import FitnessLLM
from fitness_tracker.sync.apple_health_tracker.sync import AppleHealthToFitnessTrackerSyncronizer
from fitness_tracker.sync.hevy_tracker.sync import HevyToFitnessTrackerSyncronizer
from fitness_tracker.sync.hevy_true_coach.sync import HevyToTrueCoachSyncronizer
from fitness_tracker.sync.tracker_hevy.sync import TrackerToHevySyncronizer
from fitness_tracker.sync.true_coach_hevy.sync import TrueCoachToHevySyncronizer
from fitness_tracker.sync.true_coach_tracker.sync import TrueCoachToFitnessTrackerSyncronizer
from fitness_tracker.sync.tracker_true_coach.sync import TrackerToTrueCoachSyncronizer


class Syncronizer:
    """Orchestrator that wires database and API clients to directional syncers."""

    def __init__(self, engine: Engine) -> None:
        """Wire API clients, Dropbox, and directional syncers to one engine.

        Args:
            engine (Engine): SQLAlchemy engine backing :class:`~fitness_tracker.database.Store`.
        """
        self._store = Store(engine)
        self._hevy_app = HevyAppClient()
        self._dbx = dropbox.Dropbox(os.environ["DROPBOX_ACCESS_TOKEN"])
        self._true_coach = TrueCoachClient()
        self._llm = FitnessLLM("gpt-4o-mini-2024-07-18")
        self.true_coach_to_hevy = TrueCoachToHevySyncronizer(
            store=self._store, source=self._true_coach, target=self._hevy_app, llm=self._llm
        )
        self.hevy_to_tracker = HevyToFitnessTrackerSyncronizer(
            store=self._store, source=self._hevy_app, llm=self._llm
        )
        self.hevy_to_true_coach = HevyToTrueCoachSyncronizer(
            store=self._store, target=self._true_coach
        )
        self.true_coach_to_tracker = TrueCoachToFitnessTrackerSyncronizer(
            store=self._store, source=self._true_coach
        )
        self.tracker_to_hevy = TrackerToHevySyncronizer(
            store=self._store, source=self._true_coach, target=self._hevy_app, llm=self._llm
        )
        self.apple_health_to_tracker = AppleHealthToFitnessTrackerSyncronizer(
            store=self._store, source=self._dbx
        )
        self.tracker_to_true_coach = TrackerToTrueCoachSyncronizer(
            store=self._store, target=self._true_coach
        )
