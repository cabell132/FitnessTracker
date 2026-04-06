"""Tests verifying that adapters satisfy their port protocols."""

from __future__ import annotations

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
    TrueCoachAssessmentWriter,
    TrueCoachWorkoutItemWriter,
)


class TestAdapterProtocolConformance:
    """Each adapter must be an instance of its port protocol."""

    def test_hevy_event_source(self) -> None:
        from unittest.mock import MagicMock

        adapter = HevyWorkoutEventSourceAdapter(MagicMock())
        assert isinstance(adapter, HevyWorkoutEventSource)

    def test_hevy_routine_writer(self) -> None:
        from unittest.mock import MagicMock

        adapter = HevyRoutineWriterAdapter(MagicMock())
        assert isinstance(adapter, HevyRoutineWriter)

    def test_hevy_workout_writer(self) -> None:
        from unittest.mock import MagicMock

        adapter = HevyWorkoutWriterAdapter(MagicMock())
        assert isinstance(adapter, HevyWorkoutWriter)

    def test_hevy_exercise_template_lookup(self) -> None:
        from unittest.mock import MagicMock

        adapter = HevyExerciseTemplateLookupAdapter(MagicMock())
        assert isinstance(adapter, HevyExerciseTemplateLookup)

    def test_true_coach_item_writer(self) -> None:
        from unittest.mock import MagicMock

        adapter = TrueCoachWorkoutItemWriterAdapter(MagicMock())
        assert isinstance(adapter, TrueCoachWorkoutItemWriter)

    def test_true_coach_assessment_writer(self) -> None:
        from unittest.mock import MagicMock

        adapter = TrueCoachAssessmentWriterAdapter(MagicMock())
        assert isinstance(adapter, TrueCoachAssessmentWriter)

    def test_dropbox_health_export(self) -> None:
        from unittest.mock import MagicMock

        adapter = DropboxHealthExportAdapter(MagicMock())
        assert isinstance(adapter, HealthExportStore)
