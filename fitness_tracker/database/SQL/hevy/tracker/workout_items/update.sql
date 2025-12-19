With TrueCoachTable AS (
SELECT tcwi.id, tcwi.name, tcwi.position as "order", e.id as exercise_id
FROM Workout w
LEFT JOIN TrueCoachWorkout tcw ON w.true_coach_id = tcw.id
LEFT JOIN TrueCoachWorkoutItem tcwi ON tcw.id = tcwi.workout_id
LEFT JOIN Exercise e ON tcwi.exercise_id = e.true_coach_id
WHERE w.true_coach_id = :true_coach_id
),
HevyAppTable AS (
SELECT hwi.id, hwi.name, hwi."index" + 1 as "order", e.id as exercise_id
FROM Workout w
LEFT JOIN HevyAppWorkout hw ON w.hevy_app_id = hw.id
LEFT JOIN HevyAppWorkoutItem hwi ON hw.id = hwi.workout_id
LEFT JOIN Exercise e ON hwi.exercise_id = e.hevy_app_id
WHERE w.true_coach_id = :true_coach_id
),
JoinedTable AS (
    SELECT tct.id as true_coach_id, tct.name, tct."order", ht.id as hevy_app_id, ht.name, ht."order"
    FROM TrueCoachTable tct
    JOIN HevyAppTable ht ON tct."order" = ht."order"
    WHERE tct.exercise_id = ht.exercise_id
)

UPDATE WorkoutItem
SET hevy_app_id = (
    SELECT jt.hevy_app_id
    FROM JoinedTable jt
    WHERE WorkoutItem.true_coach_id = jt.true_coach_id
)
WHERE EXISTS (
    SELECT 1
    FROM JoinedTable jt
    WHERE WorkoutItem.true_coach_id = jt.true_coach_id
);

