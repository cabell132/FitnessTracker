from fitness_tracker.llm.fitness_llm import FitnessLLM
from sqlalchemy import text
from sqlalchemy import create_engine
from fitness_tracker.database.connection import Database
from pprint import pprint
import logging
from tqdm import tqdm

# Set the logging level for SQLAlchemy and Alembic to WARNING
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

# Optionally, configure the root logger to suppress debug logs globally
logging.basicConfig(level=logging.WARNING)

# Your application code here

engine = create_engine('sqlite:///fitness_tracker.db')

db = Database(engine)
llm = FitnessLLM(model_name='gpt-4o-mini-2024-07-18', temperature=0)

with db.tracker.get_session() as session:
    try:
        res = session.execute(text("""
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
        """)).fetchall()
        # convert to rows to dict
        for row in tqdm(res[18:]):
            data = dict(row)
            print("\nInput data")
            pprint(data)
            res = llm.parse_the_sets(str(data))
            print("Output data")
            print("Number of sets: ", len(res.sets))
            pprint(res.model_dump())

            reply = input("Press Y to accept the data: ")

            if reply.upper() == 'Y':
                for i, set in enumerate(res.sets):
                    session.execute(text("""INSERT INTO Sets (workout_item_id, "index", type, reps, weight_kg, distance_meters, duration_seconds) VALUES (:workout_item_id, :idx, :type, :reps, :weight_kg, :distance_meters, :duration_seconds)"""), {
                        "workout_item_id": data['workout_item_id'],
                        "idx": i,
                        "type": set.type,
                        "reps": set.reps,
                        "weight_kg": set.weight_kg,
                        "distance_meters": set.distance_meters,
                        "duration_seconds": set.duration_seconds,
                    })
            session.commit()
    except:
        session.commit()
        raise

    session.commit()
