"""Interactive scratch pad for ad-hoc set parsing and database operations."""

import logging
from pprint import pprint

from sqlalchemy import create_engine, text
from tqdm import tqdm

from fitness_tracker.database.store import Store
from fitness_tracker.llm.fitness_llm import FitnessLLM

# Set the logging level for SQLAlchemy and Alembic to WARNING
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Optionally, configure the root logger to suppress debug logs globally
logging.basicConfig(level=logging.WARNING)

# Your application code here

engine = create_engine("sqlite:///fitness_tracker.db")

store = Store(engine)
llm = FitnessLLM(model_name="gpt-4o-mini-2024-07-18", temperature=0)

with store.unit_of_work() as uow:
    try:
        res = uow.execute(
            text("""
        SELECT
            wi.id as workout_item_id,
            twi.info as info,
            he.type as exercise_type
        FROM WorkoutItem wi
        JOIN TrueCoachWorkoutItem twi on wi.true_coach_id = twi.id
        JOIN Exercise e on e.id = wi.exercise_id
        JOIN HevyAppExercise he on he.id = e.hevy_app_id
        WHERE wi.hevy_app_id is null
        AND workout_item_id not in (SELECT workout_item_id FROM Sets)
        AND comment = "" AND info != ""
        AND twi.state = "completed"
        """)
        ).fetchall()
        # convert to rows to dict
        for row in tqdm(res[18:]):
            data = dict(row)
            print("\nInput data")  # noqa: T201
            pprint(data)  # noqa: T203
            res = llm.parse_the_sets(str(data))
            print("Output data")  # noqa: T201
            print("Number of sets: ", len(res.sets))  # noqa: T201
            pprint(res.model_dump())  # noqa: T203

            reply = input("Press Y to accept the data: ")

            if reply.upper() == "Y":
                for i, set_item in enumerate(res.sets):
                    uow.execute(
                        text(
                            'INSERT INTO Sets (workout_item_id, "index", type,'
                            " reps, weight_kg, distance_meters, duration_seconds)"
                            " VALUES (:workout_item_id, :idx, :type, :reps,"
                            " :weight_kg, :distance_meters, :duration_seconds)"
                        ),
                        {
                            "workout_item_id": data["workout_item_id"],
                            "idx": i,
                            "type": set_item.type,
                            "reps": set_item.reps,
                            "weight_kg": set_item.weight_kg,
                            "distance_meters": set_item.distance_meters,
                            "duration_seconds": set_item.duration_seconds,
                        },
                    )
            uow.commit()
    except:
        uow.commit()
        raise
