-- INSERT INTO WorkoutItem(workout_id, true_coach_id, position, exercise_id, rest)
-- 	SELECT w.id as workout_id, twi.id as  true_coach_id, position, e.id as exercise_id, 90 as rest
-- 	FROM TrueCoachWorkoutItem twi
-- 	JOIN Exercise e on e.true_coach_id = twi.exercise_id
-- 	JOIN Workout w on w.true_coach_id = twi.workout_id
-- 	WHERE twi.id NOT IN (SELECT true_coach_id FROM WorkoutItem)
-- 	ORDER BY twi.workout_id, twi.position;

-- INSERT INTO WorkoutItem(workout_id, true_coach_id, position, exercise_id, rest)
--     SELECT w.id as workout_id, twi.id as  true_coach_id, position, 200 as exercise_id, 90 as rest
-- 	FROM TrueCoachWorkoutItem twi
-- 	JOIN Workout w on w.true_coach_id = twi.workout_id
-- 	WHERE twi.id NOT IN (SELECT true_coach_id FROM WorkoutItem) AND twi.exercise_id IS NULL
-- 	ORDER BY twi.workout_id, twi.position

INSERT INTO WorkoutItem(workout_id, true_coach_id, position, exercise_id, rest)
SELECT 
    w.id as workout_id, 
    twi.id as true_coach_id, 
    twi.position, 
    CASE 
        WHEN twi.exercise_id IS NULL THEN 200 
        ELSE e.id 
    END as exercise_id, 
    90 as rest
FROM TrueCoachWorkoutItem twi
LEFT JOIN Exercise e ON e.true_coach_id = twi.exercise_id
JOIN Workout w ON w.true_coach_id = twi.workout_id
WHERE twi.id NOT IN (SELECT true_coach_id FROM WorkoutItem)
ORDER BY twi.workout_id, twi.position;

-- SELECT *
-- FROM TrueCoachWorkoutItem wi
-- WHERE wi.exercise_id IS NOT NULL
-- AND wi.exercise_id NOT IN (
-- SELECT true_coach_id
-- FROM Exercise
-- WHERE hevy_app_id IS NOT NULL
-- ) AND state = "completed"
-- GROUP BY wi.exercise_id
-- order by workout_id;

-- SELECT *
-- FROM TrueCoachWorkoutItem wi
-- WHERE wi.exercise_id IS NOT NULL
-- AND wi.exercise_id NOT IN (
-- SELECT true_coach_id
-- FROM Exercise
-- WHERE hevy_app_id IS NOT NULL
-- ) AND state = "completed"

-- INSERT INTO Exercise(name, true_coach_id)
-- 	SELECT twi.name, exercise_id as true_coach_id
-- 	FROM TrueCoachWorkoutItem twi
-- 	LEFT JOIN Exercise e ON e.true_coach_id = twi.exercise_id
-- 	WHERE e.id is null
-- 	GROUP BY twi.exercise_id;