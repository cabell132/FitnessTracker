# Create Hevy Routine From True Coach

Create Hevy Routine(s) from True Coach Workout(s) due on a given day.

## Usage

`/create-hevy-routine 2026-05-18`

Also accept natural day arguments such as `today`, `tomorrow`, or `yesterday`, but resolve them to an absolute `YYYY-MM-DD` date before running commands.

## Workflow

1. Resolve `$ARGUMENTS` to a single target date in `YYYY-MM-DD` format.
   - If no argument is provided, ask for the target date.
   - Be explicit about the resolved date before doing Hevy writes.

2. Check the working tree.

   ```powershell
   git status --short --branch
   ```

   Do not revert unrelated user changes. Runtime checkpoint files may be dirty; mention them if present.

3. Find True Coach Workouts due on that date from the local DB.

   ```powershell
   sqlite3 -header -column fitness_tracker.db "SELECT id, title, due, state, rest_day FROM TrueCoachWorkout WHERE date(due) = 'YYYY-MM-DD' ORDER BY due, id;"
   ```

   If no rows are found, stop and report that the local DB has no True Coach Workouts due on that date.

4. For each non-rest-day workout, generate a sync review.

   ```powershell
   uv run fitness-tracker sync-review truecoach-to-hevy --workout-id WORKOUT_ID
   ```

5. Inspect the report and plan.

   ```powershell
   Get-Content reports/sync-review/truecoach-to-hevy/WORKOUT_ID/report.md
   ```

   If the report has blocking Agent Next Actions, stop and summarize the blockers. Do not apply.

6. Ensure required Hevy templates from the plan.

   First dry-run:

   ```powershell
   uv run fitness-tracker hevy-templates ensure-from-plan reports/sync-review/truecoach-to-hevy/WORKOUT_ID/plan.json --dry-run
   ```

   If the dry-run is clean and templates need creating, run:

   ```powershell
   uv run fitness-tracker hevy-templates ensure-from-plan reports/sync-review/truecoach-to-hevy/WORKOUT_ID/plan.json --yes
   ```

   Then regenerate the review:

   ```powershell
   uv run fitness-tracker sync-review truecoach-to-hevy --workout-id WORKOUT_ID
   ```

7. Generate the exact Hevy request body without writing to Hevy.

   ```powershell
   uv run fitness-tracker sync-apply truecoach-to-hevy --workout-id WORKOUT_ID --dry-run
   ```

   Inspect `reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.json` if needed.

8. Apply only if the dry-run succeeds and there are no blocking actions.

   ```powershell
   uv run fitness-tracker sync-apply truecoach-to-hevy --workout-id WORKOUT_ID
   ```

9. Report the result.
   - List each processed True Coach Workout ID and title.
   - List generated report, plan, and Hevy request paths.
   - Mention any skipped rest days or blockers.
   - Mention any dirty runtime checkpoint files left in the working tree.

