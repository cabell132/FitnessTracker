"""Fitness tracker sync orchestrator — runs all platform syncs end-to-end."""

from datetime import UTC, datetime
from pathlib import Path

import urllib3
from sqlalchemy import create_engine

from fitness_tracker.sync import SyncDeps, SyncService
from logs import WideEvent

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

engine = create_engine("sqlite:///fitness_tracker.db")

sync = SyncService(SyncDeps.from_engine(engine))

with WideEvent(operation="sync_run") as run:
    sync.sync_apple_health()

    with Path("hevy_last_sync.txt").open() as f:
        previous = datetime.fromisoformat(f.read())

    now = datetime.now(tz=UTC)

    events = sync.sync_hevy_workouts(since=previous)
    run.set(hevy_event_count=len(events))

    with Path("hevy_last_sync.txt").open("w") as f:
        f.write(now.isoformat())

    sync.sync_assessments()

    deleted = sync.clear_hevy_routines()
    run.set(hevy_routines_deleted=deleted)

    res = sync.fetch_recent_true_coach_workouts()
    if res is not None:
        sync.sync_true_coach_workouts(res)

    workouts = sync.get_due_workouts()
    run.set(true_coach_workouts_synced=len(workouts))
    for workout in workouts:
        sync.create_hevy_routine(workout.id)
