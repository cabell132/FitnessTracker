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
   uv run fitness-tracker workout-backfill review --workout-id WORKOUT_ID
   uv run fitness-tracker workout-backfill inspect --review-dir reports/workout-backfill/WORKOUT_ID
   ```

   If there are blockers, stop and summarize them. Do not apply while blockers remain.

4. Inspect Apple Health evidence.

   ```bash
   sed -n '1,260p' reports/workout-backfill/WORKOUT_ID/apple-health-evidence.json
   ```

   Use Apple Health as evidence, not as an automatic source of truth. Walking to/from the gym may show as Outdoor Walk intervals around the workout. Cycling, elliptical, or elevated heart-rate blocks may indicate warmup, cooldown, commute, or workout activity depending on the True Coach content and timing.

5. Read the generated artifacts when needed.

   ```bash
   sed -n '1,260p' reports/workout-backfill/WORKOUT_ID/report.md
   sed -n '1,260p' reports/workout-backfill/WORKOUT_ID/decisions.json
   sed -n '1,260p' reports/workout-backfill/WORKOUT_ID/decision-validation.json
   ```

6. Make Agent decisions only where judgement is needed.

   Edit `reports/workout-backfill/WORKOUT_ID/decisions.json` if needed.

   Appropriate Agent decisions:
   - Set `selected_start_time` and `selected_end_time` from Apple Health, True Coach timing, and workout structure.
   - Resolve Choice Workout Items where Ross prescribed options and the athlete result names the performed choice. If the Athlete result clearly names multiple performed modalities, such as `Stairs 10mins/663 steps` and `Cycle 20mins/193kcal`, treat them as separate performed Hevy exercise blocks rather than forcing one placeholder template.
   - Resolve split Circuit/AMRAP movement templates listed under `circuit_items`.
     The backfill review may expand one True Coach circuit item into multiple
     performed movement items. Pick concrete Hevy templates for movements that
     were performed or presumed performed. Do not use generic placeholder
     templates for split circuit movements.
   - Add notes only for information not already readable from structured sets, such as athlete comments like "box disappeared after round 1".
   - Leave uncertain fields blank rather than inventing values.

   Rules:
   - Do not duplicate readable set data into exercise notes.
   - Preserve supersets from the True Coach workout order.
   - Split Circuit/AMRAP movements are grouped with a Hevy `superset_id`.
   - Prescribed circuit movement targets may be used as performed set values
     when the athlete comment does not contradict them.
   - Round-duration comments such as `2 min 10 sec` are completed round times,
     not movement durations. Use the number of round-time lines as completed
     round count and preserve the times in notes.
   - If the athlete comment gives a lower completed round count, such as
     `3 Rounds`, use that count rather than the prescribed count.
   - If the athlete comment clearly omits a movement, such as `W/o Cycle`, omit
     that movement and preserve the comment in notes.
   - If the comment names a replacement movement, require a clear template
     decision before applying.
   - Hevy duration values must be integer seconds.
   - Hevy does not accept zero-set exercises. Intentional non-set movements such as `Down Regulate` should use a deterministic fallback set, currently 4 minutes.
   - Placeholder Rest items with no meaningful performance should remain omitted.
   - Placeholder Choice/cardio items with clear performed modalities should be split into those performed exercises, preserving non-structured values such as steps or calories in notes when Hevy cannot represent them structurally.
   - Backfill apply/repair may persist synthetic local tracker Workout Items
     for split circuit movements. This is expected; it gives each created Hevy
     exercise row a one-to-one local link.
   - Current circuit movement template matching is conservative. Prefer
     explicit decisions or existing tracker-linked templates over fuzzy guesses
     for names like `PullUps`, `Push Ups`, `Row`, or `DB Push Press`.

7. Write the reviewed Hevy Workout request after editing decisions.

   ```bash
   uv run fitness-tracker workout-backfill write-request --review-dir reports/workout-backfill/WORKOUT_ID --force
   uv run fitness-tracker workout-backfill inspect --review-dir reports/workout-backfill/WORKOUT_ID
   ```

   Re-check blockers, warnings, request exercise count, notes, and supersets.

8. Diff the request against the linked local Hevy cache.

   ```bash
   uv run fitness-tracker workout-backfill diff --review-dir reports/workout-backfill/WORKOUT_ID
   ```

   If the workout is already linked and the diff is clean, do not create another Hevy Workout. Report that the local cache matches the generated request.

9. Apply or repair.

   If no linked local Hevy Workout exists and the request is ready:

   ```bash
   uv run fitness-tracker workout-backfill apply --review-dir reports/workout-backfill/WORKOUT_ID
   ```

   If a remote Hevy Workout already exists or local links are incomplete, repair local links instead of creating a duplicate:

   ```bash
   uv run fitness-tracker workout-backfill link-workout --review-dir reports/workout-backfill/WORKOUT_ID
   ```

10. Verify after applying or repairing.

   ```bash
   uv run fitness-tracker workout-backfill diff --review-dir reports/workout-backfill/WORKOUT_ID
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
   - Any Circuit/AMRAP movement template decisions, omissions, or synthetic
     tracker items created/repaired.
   - Any omitted placeholder items.
   - Report, decisions, and request artifact paths.
   - Final diff result.
   - When a Hevy Workout id is known, include: `https://hevy.com/workout/HEVY_WORKOUT_ID`
   - Any unrelated dirty files left in the working tree.
