"""Fitness tracker sync orchestrator — runs all platform syncs end-to-end."""

from datetime import UTC, datetime
from pathlib import Path

import urllib3

from fitness_tracker.apis.hevy_app.client import HevyAppClient
from fitness_tracker.apis.hevy_app.types import UpdatedWorkout
from fitness_tracker.apis.true_coach.client import TrueCoachClient
from fitness_tracker.database import Store
from fitness_tracker.sync import Syncronizer
from logs import WideEvent
from sqlalchemy import create_engine

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

true_coach = TrueCoachClient()
hevy_app = HevyAppClient()

engine = create_engine("sqlite:///fitness_tracker.db")

store = Store(engine)

sync = Syncronizer(engine)

with WideEvent(operation="sync_run") as run:
    sync.apple_health_to_tracker.sync_metrics()
    sync.apple_health_to_tracker.sync_workouts()

    with Path("hevy_last_sync.txt").open() as f:
        previous = datetime.fromisoformat(f.read())

    now = datetime.now(tz=UTC)

    events = sync.hevy_to_tracker.sync_workouts(since=previous)
    run.set(hevy_event_count=len(events))

    # Save the previous sync time
    with Path("hevy_last_sync.txt").open("w") as f:
        f.write(now.isoformat())

    with store.unit_of_work() as uow:
        for event in events:
            if isinstance(event, UpdatedWorkout):
                sync.hevy_to_true_coach.sync_workout(event.workout.id)

    sync.tracker_to_true_coach.sync_assessments()

    routines = hevy_app.routines.get(page=1, per_page=10)
    for routine in routines.routines:
        hevy_app.routines.delete(routine.id)
    run.set(hevy_routines_deleted=len(routines.routines))

    res = true_coach.workouts.get(
        order="desc", page=1, per_page=10, states=["pending", "completed", "missed"],
    )
    sync.true_coach_to_tracker.sync_workouts(res)

    with store.unit_of_work() as uow:
        due = datetime.now(tz=UTC).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        workouts = uow.tc_get_workouts(due=due)
        run.set(true_coach_workouts_synced=len(workouts))
        for workout in workouts:
            sync.true_coach_to_hevy.sync_workout(workout.id)
