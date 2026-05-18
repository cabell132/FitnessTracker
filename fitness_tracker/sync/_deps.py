"""Dependency bundle for the sync module.

Production code calls :meth:`SyncDeps.from_config` to build everything from a
single SQLAlchemy engine.  Tests construct ``SyncDeps`` directly with fakes.
"""

from __future__ import annotations

from dataclasses import dataclass

import dropbox
from sqlalchemy.engine import Engine

from fitness_tracker.apis import HevyAppClient, TrueCoachClient
from fitness_tracker.config import Config
from fitness_tracker.database import Store
from fitness_tracker.llm.fitness_llm import FitnessLLM
from fitness_tracker.sync.adapters.file_checkpoint_store import FileCheckpointStore
from fitness_tracker.sync.ports.checkpoint_store import CheckpointStore


@dataclass
class SyncDeps:
    """All external dependencies needed by :class:`SyncService`.

    Tests construct directly with fakes; production uses :meth:`from_config`.
    """

    store: Store
    hevy: HevyAppClient
    true_coach: TrueCoachClient
    llm: FitnessLLM
    dbx: dropbox.Dropbox
    checkpoints: CheckpointStore

    @classmethod
    def from_config(cls, engine: Engine, cfg: Config) -> SyncDeps:
        """Factory for production dependency wiring.

        Args:
            engine (Engine): SQLAlchemy engine backing the Store.
            cfg (Config): Application configuration.

        Returns:
            SyncDeps: Fully wired dependency bundle.
        """
        hevy = HevyAppClient(
            api_key=cfg.hevy_api_key.get_secret_value(),
            web_api_key=cfg.hevy_web_api_key.get_secret_value(),
        )
        return cls(
            store=Store(engine, hevy_client=hevy),
            hevy=hevy,
            true_coach=TrueCoachClient(
                email=cfg.email,
                password=cfg.truecoach_password.get_secret_value(),
            ),
            llm=FitnessLLM(
                cfg.llm_model,
                api_key=cfg.openai_api_key.get_secret_value(),
                temperature=cfg.llm_temperature,
                max_completion_tokens=cfg.llm_max_tokens,
            ),
            dbx=dropbox.Dropbox(cfg.dropbox_access_token.get_secret_value()),
            checkpoints=FileCheckpointStore(),
        )
