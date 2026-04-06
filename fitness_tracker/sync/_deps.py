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
from fitness_tracker.sync._fallback_set_parser import FallbackSetParser
from fitness_tracker.sync._true_coach_html import HtmlFallbackSetParser
from fitness_tracker.sync.adapters import (
    DropboxHealthExportAdapter,
    HevyExerciseTemplateLookupAdapter,
    HevyRoutineWriterAdapter,
    HevyWorkoutEventSourceAdapter,
    HevyWorkoutWriterAdapter,
    TrueCoachAssessmentWriterAdapter,
    TrueCoachWorkoutItemWriterAdapter,
)
from fitness_tracker.sync.ports import (
    HealthExportStore,
    HevyExerciseTemplateLookup,
    HevyRoutineWriter,
    HevyWorkoutEventSource,
    HevyWorkoutWriter,
    SetParser,
    StoreLike,
    TrueCoachAssessmentWriter,
    TrueCoachWorkoutItemWriter,
    WorkoutItemLinker,
)


@dataclass
class SyncDeps:
    """All external dependencies needed by :class:`SyncService`.

    Each field is typed as a port protocol so that tests can inject fakes
    directly.  Production uses :meth:`from_engine` to wrap concrete clients
    in adapters.
    """

    store: StoreLike
    hevy_event_source: HevyWorkoutEventSource
    hevy_routine_writer: HevyRoutineWriter
    hevy_workout_writer: HevyWorkoutWriter
    hevy_template_lookup: HevyExerciseTemplateLookup
    tc_item_writer: TrueCoachWorkoutItemWriter
    tc_assessment_writer: TrueCoachAssessmentWriter
    health_export: HealthExportStore
    set_parser: SetParser
    item_linker: WorkoutItemLinker

    # --- retained for convenience methods on SyncService that need raw clients ---
    hevy: HevyAppClient | None = None
    true_coach: TrueCoachClient | None = None

    @classmethod
    def from_engine(cls, engine: Engine) -> SyncDeps:
        """One-arg factory for production -- the only place that reads env vars.

        Args:
            engine (Engine): SQLAlchemy engine backing the Store.

        Returns:
            SyncDeps: Fully wired dependency bundle.
        """
        hevy = HevyAppClient()
        tc = TrueCoachClient()
        llm = FitnessLLM("gpt-4o-mini-2024-07-18")
        dbx = dropbox.Dropbox(os.environ["DROPBOX_ACCESS_TOKEN"])

        return cls(
            store=Store(engine),
            hevy_event_source=HevyWorkoutEventSourceAdapter(hevy),
            hevy_routine_writer=HevyRoutineWriterAdapter(hevy),
            hevy_workout_writer=HevyWorkoutWriterAdapter(hevy),
            hevy_template_lookup=HevyExerciseTemplateLookupAdapter(hevy),
            tc_item_writer=TrueCoachWorkoutItemWriterAdapter(tc),
            tc_assessment_writer=TrueCoachAssessmentWriterAdapter(tc),
            health_export=DropboxHealthExportAdapter(dbx),
            set_parser=FallbackSetParser(llm, HtmlFallbackSetParser()),
            item_linker=llm,
            hevy=hevy,
            true_coach=tc,
        )
