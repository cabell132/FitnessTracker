"""Scale history import through the public sync function."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fitness_tracker.apis.vesync.models.weight import WeightDataPage, WeightMeasurement
from fitness_tracker.database.models.vesync import VeSyncWeighIn
from fitness_tracker.sync._deps import SyncDeps
from fitness_tracker.sync._service import SyncService
from fitness_tracker.sync.adapters.file_checkpoint_store import InMemoryCheckpointStore
from fitness_tracker.sync.vesync import sync_vesync_weigh_ins
from fitness_tracker.sync_review.true_coach_to_hevy import RoutineReplacementBatchResult


class FakeVeSync:
    def __init__(self, measurements: list[WeightMeasurement]) -> None:
        self.measurements = measurements
        self.calls: list[int] = []
        self.weight = self

    def find_scale(self) -> SimpleNamespace:
        return SimpleNamespace(cid="scale-1")

    def get_weight_data_v2(
        self, _device: SimpleNamespace, *, page: int, page_size: int
    ) -> WeightDataPage:
        self.calls.append(page)
        start = (page - 1) * page_size
        return WeightDataPage(measurements=self.measurements[start : start + page_size])


def test_imports_all_pages_without_mixing_profiles_or_duplicating_rows(store) -> None:
    own = [
        WeightMeasurement(
            timestamp=1_720_000_000 + index,
            weight_kg=80.0,
            impedance=500.0,
            age=40,
            height_cm=180.0,
            gender="2",
        )
        for index in range(100)
    ]
    spouse = WeightMeasurement(
        timestamp=1_720_000_200,
        weight_kg=60.0,
        sub_user_id="other-profile",
    )
    source = FakeVeSync([*own, spouse])

    first = sync_vesync_weigh_ins(store, source)
    second = sync_vesync_weigh_ins(store, source)

    assert source.calls == [1, 2, 1, 2]
    assert (first.scanned, first.inserted, first.excluded) == (101, 100, 1)
    assert (second.inserted, second.updated) == (0, 0)
    rows = store.query_all(VeSyncWeighIn)
    assert len(rows) == 100
    assert all(row.impedance_ohms == 500.0 for row in rows)
    assert all(row.body_fat_pct is not None for row in rows)
    assert {"age", "height_cm", "gender", "sub_user_id"}.isdisjoint(VeSyncWeighIn.columns())


def test_refreshes_measurement_details_and_keeps_missing_values_null(store) -> None:
    reading = WeightMeasurement(timestamp=1_720_000_000, weight_kg=80.0)
    source = FakeVeSync([reading])

    assert sync_vesync_weigh_ins(store, source).inserted == 1
    row = store.query_all(VeSyncWeighIn)[0]
    assert row.impedance_ohms is None
    assert row.body_fat_pct is None

    reading.impedance = 500.0
    reading.age = 40
    reading.height_cm = 180.0
    reading.gender = "2"
    assert sync_vesync_weigh_ins(store, source).updated == 1
    row = store.query_all(VeSyncWeighIn)[0]
    assert row.impedance_ohms == 500.0
    assert row.body_fat_pct is not None


def test_athlete_mode_recalculates_existing_readings(store) -> None:
    reading = WeightMeasurement(
        timestamp=1_720_000_000,
        weight_kg=74.55,
        impedance=526,
        age=43,
        height_cm=170,
        gender="2",
    )
    source = FakeVeSync([reading])

    assert sync_vesync_weigh_ins(store, source).inserted == 1
    assert store.query_all(VeSyncWeighIn)[0].body_fat_pct == 20.7

    result = sync_vesync_weigh_ins(store, source, athlete_mode=True)

    assert (result.inserted, result.updated) == (0, 1)
    assert store.query_all(VeSyncWeighIn)[0].body_fat_pct == 14.5


def test_full_sync_imports_scale_even_without_new_workouts(
    store, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = FakeVeSync(
        [
            WeightMeasurement(
                timestamp=1_720_000_000,
                weight_kg=74.55,
                impedance=526,
                age=43,
                height_cm=170,
                gender="2",
            )
        ]
    )
    deps = SyncDeps(
        store=store,
        hevy=MagicMock(),
        true_coach=MagicMock(),
        llm=MagicMock(),
        dbx=MagicMock(),
        checkpoints=InMemoryCheckpointStore(),
        vesync=source,
        vesync_athlete_mode=True,
    )
    service = SyncService(deps)
    monkeypatch.setattr(service, "sync_apple_health", lambda: None)
    monkeypatch.setattr(service, "fetch_recent_true_coach_workouts", lambda: None)
    monkeypatch.setattr(service, "sync_hevy_workouts", lambda since: [])
    monkeypatch.setattr(service, "sync_assessments", lambda: None)
    monkeypatch.setattr(service, "get_due_workouts", lambda **_: [])
    monkeypatch.setattr(
        service,
        "replace_due_hevy_routines",
        lambda workouts: RoutineReplacementBatchResult(
            status="no_due_workouts", review_bundles=[], apply_results=[]
        ),
    )

    service.run()

    rows = store.query_all(VeSyncWeighIn)
    assert len(rows) == 1
    assert rows[0].body_fat_pct == 14.5
    assert source.calls == [1]
