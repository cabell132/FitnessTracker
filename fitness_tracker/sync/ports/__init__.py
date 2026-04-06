"""Port definitions for the sync module's cross-boundary dependencies.

Each Protocol represents what the sync module *needs* from an external system,
not a mirror of the external system's full API surface.

Design decisions
----------------
1. **Role-oriented, not system-oriented ports.**  The sync module does four
   distinct things with Hevy: read events, create routines, create workouts,
   and look up exercise templates.  These are separate protocols so that each
   syncer declares exactly the capabilities it needs, and test doubles stay tiny.

2. **The Store/UoW boundary stays as-is.**  The Store already accepts an
   in-memory SQLite engine and the UoW is a context-manager -- that *is* the
   port.  We add a ``StoreLike`` protocol so syncers can be typed against it
   without importing the concrete ``Store``.

3. **Domain types (Pydantic models) remain shared.**  Types like
   ``PostRoutinesRequestBody`` and ``PaginatedWorkoutEvents`` are pure data
   shapes with no I/O -- they *are* the contract.  Duplicating them behind the
   port adds noise with no decoupling benefit.

4. **Dropbox disappears behind a domain concept.**  The sync module does not
   need "a Dropbox client"; it needs "a way to list and download health export
   CSVs."  The port is ``HealthExportStore``, not ``DropboxLike``.

5. **LLM ports are split by capability.**  ``SetParser`` and ``WorkoutItemLinker``
   are independently mockable: some syncers need one, some the other, none need
   both except ``HevyToFitnessTrackerSyncronizer``.
"""

from fitness_tracker.sync.ports.file_entry import FileEntry
from fitness_tracker.sync.ports.health_export_store import HealthExportStore
from fitness_tracker.sync.ports.hevy_exercise_template_lookup import HevyExerciseTemplateLookup
from fitness_tracker.sync.ports.hevy_routine_writer import HevyRoutineWriter
from fitness_tracker.sync.ports.hevy_workout_event_source import HevyWorkoutEventSource
from fitness_tracker.sync.ports.hevy_workout_writer import HevyWorkoutWriter
from fitness_tracker.sync.ports.set_parser import SetParser
from fitness_tracker.sync.ports.store_like import StoreLike
from fitness_tracker.sync.ports.true_coach_assessment_writer import TrueCoachAssessmentWriter
from fitness_tracker.sync.ports.true_coach_workout_item_writer import TrueCoachWorkoutItemWriter
from fitness_tracker.sync.ports.workout_item_linker import WorkoutItemLinker

__all__ = [
    "FileEntry",
    "HealthExportStore",
    "HevyExerciseTemplateLookup",
    "HevyRoutineWriter",
    "HevyWorkoutEventSource",
    "HevyWorkoutWriter",
    "SetParser",
    "StoreLike",
    "TrueCoachAssessmentWriter",
    "TrueCoachWorkoutItemWriter",
    "WorkoutItemLinker",
]
