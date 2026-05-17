SELECT tcwi.id AS true_coach_id, tcwi.name, tcwi.position AS "order"
FROM "WorkoutItem" AS wi
JOIN "Workout" w ON wi.workout_id = w.id
JOIN "TrueCoachWorkoutItem" tcwi ON wi.true_coach_id = tcwi.id
WHERE w.true_coach_id = :true_coach_id
AND wi.hevy_app_id IS NULL
