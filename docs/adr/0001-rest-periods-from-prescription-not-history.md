# Rest periods come from the coach's prescription, not training history

When the True Coach → Hevy sync sets rest timers on a generated Routine, the
rest period for each exercise is parsed from the coach's prescription text
where it is given, and falls back to a static per-exercise-type default
otherwise.

Deriving rest from the athlete's training history — the obvious approach —
was considered and rejected because the data does not exist. Hevy's
`exercise_history` records set results (weight, reps, RPE, distance,
duration) but no rest, and `rest_seconds` exists only as a prescription
field on a Routine, never as a recorded outcome on a Workout. Do not
re-introduce history-based rest.
