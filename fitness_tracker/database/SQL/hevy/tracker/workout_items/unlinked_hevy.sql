SELECT hwi.id as hevy_app_id, hwi.name, hwi."index" + 1 as "order"
FROM HevyAppWorkoutItem as hwi
JOIN HevyAppWorkout hw  ON hw.id = hwi.workout_id
JOIN Workout w ON w.hevy_app_id = hw.id
WHERE w.true_coach_id = :true_coach_id
AND hwi.id NOT IN (
    SELECT hevy_app_id
    FROM WorkoutItem
    WHERE workout_id = w.id
    AND hevy_app_id IS NOT NULL
    )
