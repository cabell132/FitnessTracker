# Workout backfill uses review artifacts and explicit Agent decisions

Workout backfill creates a logged Hevy Workout directly from an
already-completed True Coach Workout. It does not create a Hevy Routine: a
Routine is a prescription, while backfill is historical result transfer.

The local tracker `Workout`, `WorkoutItem`, and `Sets` rows are the primary
source for performed results. True Coach item names, prescription text, and
Athlete result comments remain review context. The generated Hevy Workout
should not duplicate structured set values in notes; notes are reserved for
non-structured context, Athlete feedback, and values Hevy cannot represent in
set fields.

The workflow separates deterministic evidence from judgement. Review commands
write an audit trail from local data, including a deterministic plan, a draft
Hevy Workout request, Apple Health timing evidence, and a report. Agent or
Athlete judgement belongs in editable request or decision artifacts, not by
rewriting the deterministic plan.

Timing is inferred only through review. Helper scripts may surface Apple Health
workout intervals, heart-rate patterns, and candidate workout windows, but the
CLI must not silently choose uncertain timestamps. If confidence is low,
timestamps remain unset until the Agent or Athlete selects them.

Choice Workout Items, where the Coach offers multiple exercise options and the
Athlete's result text identifies what was actually performed, are resolved
through explicit decisions when ambiguous. One Choice Workout Item may split
into multiple Hevy exercise blocks when the Athlete performed multiple
modalities.

Apply is responsible for idempotency and local linkage. Backfilled Hevy
Workouts include the source True Coach Workout id as a remote marker. Before
creating anything, apply checks whether the local tracker row is already linked
or whether a remote Hevy Workout with that marker already exists. After remote
creation, apply syncs/fetches the Hevy Workout and links the created Hevy rows
back to the existing local tracker rows. If remote creation succeeds but local
linking fails, the command must leave enough recovery information to repair the
link instead of creating a duplicate on retry.
