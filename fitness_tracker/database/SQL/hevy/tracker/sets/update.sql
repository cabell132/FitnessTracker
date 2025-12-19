UPDATE Sets
SET 
    weight_kg = (SELECT has.weight_kg 
                 FROM Workout w
                 JOIN WorkoutItem wi ON w.id = wi.workout_id
                 JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
                 JOIN HevyAppSets has ON has.workout_item_id = hawi.id
                 WHERE w.true_coach_id = :true_coach_id 
                   AND has."index" = Sets."index" 
                   AND wi.id= Sets.workout_item_id),
    reps = (SELECT has.reps 
            FROM Workout w
            JOIN WorkoutItem wi ON w.id = wi.workout_id
            JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
            JOIN HevyAppSets has ON has.workout_item_id = hawi.id
            WHERE w.true_coach_id = :true_coach_id 
              AND has."index" = Sets."index" 
              AND wi.id= Sets.workout_item_id),
    distance_meters = (SELECT has.distance_meters 
                        FROM Workout w
                        JOIN WorkoutItem wi ON w.id = wi.workout_id
                        JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
                        JOIN HevyAppSets has ON has.workout_item_id = hawi.id
                        WHERE w.true_coach_id = :true_coach_id 
                          AND has."index" = Sets."index" 
                          AND wi.id= Sets.workout_item_id),
    duration_seconds = (SELECT has.duration_seconds 
                         FROM Workout w
                         JOIN WorkoutItem wi ON w.id = wi.workout_id
                         JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
                         JOIN HevyAppSets has ON has.workout_item_id = hawi.id
                         WHERE w.true_coach_id = :true_coach_id 
                           AND has."index" = Sets."index" 
                           AND wi.id= Sets.workout_item_id),
    rpe = (SELECT has.rpe 
           FROM Workout w
           JOIN WorkoutItem wi ON w.id = wi.workout_id
           JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
           JOIN HevyAppSets has ON has.workout_item_id = hawi.id
           WHERE w.true_coach_id = :true_coach_id 
             AND has."index" = Sets."index" 
             AND wi.id= Sets.workout_item_id),
    type = (SELECT has.type 
            FROM Workout w
            JOIN WorkoutItem wi ON w.id = wi.workout_id
            JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
            JOIN HevyAppSets has ON has.workout_item_id = hawi.id
            WHERE w.true_coach_id = :true_coach_id 
              AND has."index" = Sets."index" 
              AND wi.id= Sets.workout_item_id),
    hevy_app_id = (SELECT has.id 
                   FROM Workout w
                   JOIN WorkoutItem wi ON w.id = wi.workout_id
                   JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
                   JOIN HevyAppSets has ON has.workout_item_id = hawi.id
                   WHERE w.true_coach_id = :true_coach_id 
                     AND has."index" = Sets."index" 
                     AND wi.id= Sets.workout_item_id)
WHERE EXISTS (
    SELECT 1 
    FROM Workout w
    JOIN WorkoutItem wi ON w.id = wi.workout_id
    JOIN HevyAppWorkoutItem hawi ON hawi.id = wi.hevy_app_id
    JOIN HevyAppSets has ON has.workout_item_id = hawi.id
    WHERE w.true_coach_id = :true_coach_id 
      AND has."index" = Sets."index" 
      AND wi.id= Sets.workout_item_id
);
