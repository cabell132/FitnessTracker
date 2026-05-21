"""Tests for Hevy -> tracker workout linking."""

from __future__ import annotations

from unittest.mock import MagicMock

from fitness_tracker.apis.hevy_app.types import Workout
from fitness_tracker.database.models.tracker import Workout as TrackerWorkout
from fitness_tracker.database.models.true_coach import TrueCoachWorkout
from fitness_tracker.database.store import Store
from fitness_tracker.sync.hevy_tracker.sync import HevyToFitnessTrackerSyncronizer


def test_link_workout_prefers_true_coach_workout_id_marker_from_notes(store: Store) -> None:
    """Canonical Routine-derived notes identify the source True Coach Workout."""
    _seed_tracker_workout(store, true_coach_id=47)
    _seed_tracker_workout(store, true_coach_id=999)
    syncer = HevyToFitnessTrackerSyncronizer(store=store, source=MagicMock(), llm=MagicMock())

    with store.unit_of_work() as uow:
        true_coach_id = syncer.link_workout(
            uow,
            "hevy-workout-1",
            _hevy_workout(
                title="17 May 2026\nClean Plan\n999",
                description="TrueCoachWorkoutId: 47\nRoutineBatch: truecoach-to-hevy",
            ),
        )

    linked = store.query_one(TrackerWorkout, true_coach_id=47)
    legacy_candidate = store.query_one(TrackerWorkout, true_coach_id=999)
    assert true_coach_id == 47
    assert linked is not None
    assert linked.hevy_app_id == "hevy-workout-1"
    assert legacy_candidate is not None
    assert legacy_candidate.hevy_app_id is None


def test_link_workout_falls_back_to_legacy_title_id(store: Store) -> None:
    """Older Hevy Workouts without notes still link through the title-carried id."""
    _seed_tracker_workout(store, true_coach_id=47)
    syncer = HevyToFitnessTrackerSyncronizer(store=store, source=MagicMock(), llm=MagicMock())

    with store.unit_of_work() as uow:
        true_coach_id = syncer.link_workout(
            uow,
            "hevy-workout-legacy",
            _hevy_workout(
                title="17 May 2026\nClean Plan\n47",
                description=None,
            ),
        )

    linked = store.query_one(TrackerWorkout, true_coach_id=47)
    assert true_coach_id == 47
    assert linked is not None
    assert linked.hevy_app_id == "hevy-workout-legacy"


def _seed_tracker_workout(store: Store, *, true_coach_id: int) -> None:
    with store.unit_of_work() as uow:
        uow.session.add(
            TrueCoachWorkout(
                id=true_coach_id,
                title=f"True Coach {true_coach_id}",
                state="scheduled",
                rest_day=False,
            )
        )
        uow.session.add(
            TrackerWorkout(
                title=f"Tracker {true_coach_id}",
                true_coach_id=true_coach_id,
            )
        )


def _hevy_workout(*, title: str, description: str | None) -> Workout:
    return Workout(
        id="hevy-workout-1",
        title=title,
        description=description,
        start_time="2026-05-20T10:00:00+00:00",
        end_time="2026-05-20T11:00:00+00:00",
        updated_at="2026-05-20T11:05:00+00:00",
        created_at="2026-05-20T10:00:00+00:00",
        exercises=[],
    )
