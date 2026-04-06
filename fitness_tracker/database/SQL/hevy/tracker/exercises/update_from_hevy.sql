UPDATE WorkoutItem
SET exercise_id = (
    SELECT e.id
    FROM HevyAppWorkoutItem hwi
    JOIN Exercise e ON hwi.exercise_id = e.hevy_app_id
    JOIN WorkoutItem wi ON wi.hevy_app_id = hwi.id
    JOIN Workout w ON w.id = wi.workout_id
    WHERE WorkoutItem.id = wi.id
    AND e.id IS NOT NULL
    AND w.true_coach_id = :true_coach_id
    LIMIT 1
)
WHERE EXISTS (
    SELECT 1
    FROM HevyAppWorkoutItem hwi
    JOIN Exercise e ON hwi.exercise_id = e.hevy_app_id
    JOIN WorkoutItem wi ON wi.hevy_app_id = hwi.id
    JOIN Workout w ON w.id = wi.workout_id
    WHERE WorkoutItem.id = wi.id
    AND e.id IS NOT NULL
    AND e.id != wi.exercise_id
    AND w.true_coach_id = :true_coach_id
);
