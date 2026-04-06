"""Thin adapters that wrap external API clients behind sync port protocols.

Each adapter implements exactly one port so that syncers never depend on the
full client surface.  Test doubles replace these adapters, not the clients.
"""

from fitness_tracker.sync.adapters.dropbox_health_export import DropboxHealthExportAdapter
from fitness_tracker.sync.adapters.hevy_exercise_template_lookup import (
    HevyExerciseTemplateLookupAdapter,
)
from fitness_tracker.sync.adapters.hevy_routine_writer import HevyRoutineWriterAdapter
from fitness_tracker.sync.adapters.hevy_workout_event_source import HevyWorkoutEventSourceAdapter
from fitness_tracker.sync.adapters.hevy_workout_writer import HevyWorkoutWriterAdapter
from fitness_tracker.sync.adapters.true_coach_assessment_writer import (
    TrueCoachAssessmentWriterAdapter,
)
from fitness_tracker.sync.adapters.true_coach_workout_item_writer import (
    TrueCoachWorkoutItemWriterAdapter,
)

__all__ = [
    "DropboxHealthExportAdapter",
    "HevyExerciseTemplateLookupAdapter",
    "HevyRoutineWriterAdapter",
    "HevyWorkoutEventSourceAdapter",
    "HevyWorkoutWriterAdapter",
    "TrueCoachAssessmentWriterAdapter",
    "TrueCoachWorkoutItemWriterAdapter",
]
