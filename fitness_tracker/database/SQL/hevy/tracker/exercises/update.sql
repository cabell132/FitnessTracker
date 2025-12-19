UPDATE Exercise
SET hevy_app_id = (
    SELECT hawi.exercise_id
    FROM Workout w
    JOIN WorkoutItem wi ON w.id = wi.workout_id
    JOIN TrueCoachWorkoutItem tcwi ON tcwi.id = wi.true_coach_id
    JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
    JOIN Exercise e ON tcwi.name = e.name
    WHERE w.true_coach_id = :true_coach_id AND tcwi.exercise_id IS NULL AND e.hevy_app_id IS NULL
    )
WHERE EXISTS (
    SELECT 1
    FROM Workout w
    JOIN WorkoutItem wi ON w.id = wi.workout_id
    JOIN TrueCoachWorkoutItem tcwi ON tcwi.id = wi.true_coach_id
    JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
    WHERE w.true_coach_id = :true_coach_id 
    AND tcwi.exercise_id IS NULL 
    AND Exercise.name = tcwi.name
    AND Exercise.hevy_app_id IS NULL
    )