# Backfill True Coach Workout To Hevy

Backfill one completed True Coach Workout into Hevy as a logged Workout.

## Usage

`/tc-backfill-workout 455045484`

Also accept a plain True Coach Workout id if the user invokes this command with only one argument. If no workout id is provided, ask for the True Coach Workout id.

## Workflow

1. Resolve `$ARGUMENTS` to a single True Coach Workout id.
   - Do not infer the id from dates or nearby context unless the user explicitly says to use the current context.
   - Echo the resolved id before doing Hevy writes.

2. Check the working tree.

   ```bash
   git status --short --branch
   ```

   Do not revert unrelated user changes. Runtime checkpoint files may be dirty; mention them if present.

3. Generate and inspect the deterministic backfill review.

   ```bash
   uv run fitness-tracker sync-review truecoach-workout-backfill-inspect --workout-id WORKOUT_ID
   ```

   If there are blockers, stop and summarize them. Do not apply while blockers remain.

4. Inspect Apple Health evidence.

   ```bash
   uv run fitness-tracker sync-review truecoach-workout-backfill-evidence --workout-id WORKOUT_ID
   ```

   Use Apple Health as evidence, not as an automatic source of truth. Walking to/from the gym may show as Outdoor Walk intervals around the workout. Cycling, elliptical, or elevated heart-rate blocks may indicate warmup, cooldown, commute, or workout activity depending on the True Coach content and timing.

5. Read the generated artifacts when needed.

   ```bash
   sed -n '1,260p' reports/sync-review/truecoach-workout-backfill/WORKOUT_ID/report.md
   sed -n '1,260p' reports/sync-review/truecoach-workout-backfill/WORKOUT_ID/backfill-decisions.json
   sed -n '1,260p' reports/sync-review/truecoach-workout-backfill/WORKOUT_ID/hevy-workout-request.json
   ```

6. Make Agent decisions only where judgement is needed.

   Edit `reports/sync-review/truecoach-workout-backfill/WORKOUT_ID/backfill-decisions.json` if needed.

   Appropriate Agent decisions:
   - Set `selected_start_time` and `selected_end_time` from Apple Health, True Coach timing, and workout structure.
   - Resolve Choice Workout Items where Ross prescribed options and the athlete result names the performed choice.
   - Add notes only for information not already readable from structured sets, such as athlete comments like "box disappeared after round 1".
   - Leave uncertain fields blank rather than inventing values.

   Rules:
   - Do not duplicate readable set data into exercise notes.
   - Preserve supersets from the True Coach workout order.
   - Hevy duration values must be integer seconds.
   - Hevy does not accept zero-set exercises. Intentional non-set movements such as `Down Regulate` should use a deterministic fallback set, currently 4 minutes.
   - Placeholder Rest items with no meaningful performance should remain omitted.

7. Regenerate the review after editing decisions.

   ```bash
   uv run fitness-tracker sync-review truecoach-workout-backfill-inspect --workout-id WORKOUT_ID --decisions reports/sync-review/truecoach-workout-backfill/WORKOUT_ID/backfill-decisions.json
   ```

   Re-check blockers, warnings, request exercise count, notes, and supersets.

8. Diff the request against the linked local Hevy cache.

   ```bash
   uv run fitness-tracker sync-review truecoach-workout-backfill-diff --workout-id WORKOUT_ID --decisions reports/sync-review/truecoach-workout-backfill/WORKOUT_ID/backfill-decisions.json
   ```

   If the workout is already linked and the diff is clean, do not create another Hevy Workout. Report that the local cache matches the generated request.

9. Apply or repair.

   If no linked local Hevy Workout exists and the request is ready:

   ```bash
   uv run fitness-tracker sync-apply truecoach-workout-backfill --workout-id WORKOUT_ID --decisions reports/sync-review/truecoach-workout-backfill/WORKOUT_ID/backfill-decisions.json
   ```

   If a remote Hevy Workout already exists or local links are incomplete, repair local links instead of creating a duplicate:

   ```bash
   uv run fitness-tracker sync-apply truecoach-workout-backfill-repair --workout-id WORKOUT_ID --decisions reports/sync-review/truecoach-workout-backfill/WORKOUT_ID/backfill-decisions.json
   ```

10. Verify after applying or repairing.

   ```bash
   uv run fitness-tracker sync-review truecoach-workout-backfill-diff --workout-id WORKOUT_ID --decisions reports/sync-review/truecoach-workout-backfill/WORKOUT_ID/backfill-decisions.json
   ```

   If a Hevy Workout id was created or discovered, inspect the remote workout:

   ```bash
   uv run fitness-tracker hevy workouts inspect HEVY_WORKOUT_ID
   ```

11. Report the result.
   - True Coach Workout id and title.
   - Hevy Workout id, if created, repaired, or already linked.
   - Selected start/end time and why.
   - Any Apple Health evidence used.
   - Any Choice Workout Item decisions.
   - Any omitted placeholder items.
   - Report, decisions, and request artifact paths.
   - Final diff result.
   - When a Hevy Workout id is known, include: `https://hevy.com/workout/HEVY_WORKOUT_ID`
   - Any unrelated dirty files left in the working tree.
