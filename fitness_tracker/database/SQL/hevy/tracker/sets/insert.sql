INSERT INTO Sets (workout_item_id, "index", weight_kg, type, reps, distance_meters, duration_seconds, rpe, hevy_app_id)
SELECT wi.id as workout_item_id, has."index", has.weight_kg, has.type, has.reps, has.distance_meters, has.duration_seconds, has.rpe, has.id as hevy_app_id
FROM Workout w
JOIN WorkoutItem wi ON w.id = wi.workout_id
JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
JOIN HevyAppSets has ON has.workout_item_id = hawi.id
WHERE NOT EXISTS (
    SELECT 1
    FROM Sets s
    WHERE s.workout_item_id = wi.id
    AND s."index" = has."index"
)
AND w.true_coach_id = :true_coach_id;