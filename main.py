from fitness_tracker.apis.true_coach.auth import authorize
from fitness_tracker.apis.true_coach.client import TrueCoachClient
from fitness_tracker.apis.hevy_app.client import HevyAppClient
from fitness_tracker.database import Database
from fitness_tracker.sync import Syncronizer
from sqlalchemy import create_engine
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import urllib3
from fitness_tracker.apis.hevy_app.types import UpdatedWorkout

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

true_coach = TrueCoachClient()
hevy_app = HevyAppClient()

engine = create_engine("sqlite:///fitness_tracker.db")

db = Database(engine)

sync = Syncronizer(engine)

sync.apple_health_to_tracker.sync_metrics()
sync.apple_health_to_tracker.sync_workouts()

with open("hevy_last_sync.txt", "r") as f:
    previous = datetime.fromisoformat(f.read())

now = datetime.now()


events = sync.hevy_to_tracker.sync_workouts(since=previous)

# Save the previous sync time
with open("hevy_last_sync.txt", "w") as f:
    f.write(now.isoformat())

with db.tracker.get_session() as session:
    for event in events:
        if isinstance(event, UpdatedWorkout):
            sync.hevy_to_true_coach.sync_workout(event.workout.id)

sync.tracker_to_true_coach.sync_assessments()

routines = hevy_app.routines.get(page=1, per_page=10)
for routine in routines["routines"]:
    hevy_app.routines.delete(routine["id"])

res = true_coach.workouts.get(
    order="desc", page=1, per_page=10, states=["pending", "completed", "missed"]
)
sync.true_coach_to_tracker.sync_workouts(res)


with db.tracker.get_session() as session:
    due = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )  # + relativedelta(days=2)
    workout = db.true_coach.get_workout(due=due, session=session)
    print(workout.id, workout.title)
res = sync.true_coach_to_hevy.sync_workout(workout.id)
