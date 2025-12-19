-- Step 1: Prepare the index_table using a WITH clause
WITH missedRows AS (
    SELECT
        id, -- Assuming you have a unique row ID
        workout_id,
        position,
        state,
        ROW_NUMBER() OVER (
            PARTITION BY workout_id
            ORDER BY position
        ) AS missed_index
    FROM
        TrueCoachWorkoutItem
    WHERE
        state != 'missed'
),
index_table AS (
    SELECT
        w.id AS true_coach_id,
        w.workout_id,
        w.position,
        w.state,
        CASE 
            WHEN w.state != 'missed' THEN cr.missed_index
            ELSE NULL
        END AS "index"
    FROM
        TrueCoachWorkoutItem w
    LEFT JOIN
        missedRows cr
    ON
        w.id = cr.id
)
-- Step 2: Perform the UPDATE using the prepared index_table
UPDATE WorkoutItem
SET hevy_app_id = (
    SELECT hwi.id
    FROM Workout w
    JOIN TrueCoachWorkoutItem twi ON w.true_coach_id = twi.workout_id
    JOIN HevyAppWorkout hw ON w.hevy_app_id = hw.id
    JOIN HevyAppWorkoutItem hwi ON hwi.workout_id = hw.id
    JOIN index_table idx ON idx.true_coach_id = twi.id
    WHERE idx."index" = (hwi."index" + 1)
    AND WorkoutItem.true_coach_id = twi.id
)
WHERE EXISTS (
    SELECT 1
    FROM index_table idx
    JOIN TrueCoachWorkoutItem twi ON idx.true_coach_id = twi.id
    WHERE WorkoutItem.true_coach_id = twi.id
);
