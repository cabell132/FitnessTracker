"""Dependency bundle for the sync module.

Production code calls :meth:`SyncDeps.from_engine` to build everything from a
single SQLAlchemy engine.  Tests construct ``SyncDeps`` directly with fakes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import dropbox
from sqlalchemy.engine import Engine

from fitness_tracker.apis import HevyAppClient, TrueCoachClient
from fitness_tracker.database import Store
from fitness_tracker.llm.fitness_llm import FitnessLLM


@dataclass
class SyncDeps:
    """All external dependencies needed by :class:`SyncService`.

    Tests construct directly with fakes; production uses :meth:`from_engine`.
    """

    store: Store
    hevy: HevyAppClient
    true_coach: TrueCoachClient
    llm: FitnessLLM
    dbx: dropbox.Dropbox

    @classmethod
    def from_engine(cls, engine: Engine) -> SyncDeps:
        """One-arg factory for production — the only place that reads env vars.

        Args:
            engine (Engine): SQLAlchemy engine backing the Store.

        Returns:
            SyncDeps: Fully wired dependency bundle.
        """
        return cls(
            store=Store(engine),
            hevy=HevyAppClient(),
            true_coach=TrueCoachClient(),
            llm=FitnessLLM("gpt-4o-mini-2024-07-18"),
            dbx=dropbox.Dropbox(os.environ["DROPBOX_ACCESS_TOKEN"]),
        )
