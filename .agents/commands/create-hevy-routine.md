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

   ```bash
   git status --short --branch
   ```

   Do not revert unrelated user changes. Runtime checkpoint files may be dirty; mention them if present.

3. Find True Coach Workouts due on that date from the configured database.

   ```bash
   uv run fitness-tracker truecoach due --date YYYY-MM-DD
   ```

   If no rows are found, stop and report that the configured DB has no True Coach Workouts due on that date.

4. For each non-rest-day workout, generate a sync review.

   ```bash
   uv run fitness-tracker sync-review truecoach-to-hevy --workout-id WORKOUT_ID --summary
   ```

5. Inspect the report and plan.

   ```bash
   sed -n '1,260p' reports/sync-review/truecoach-to-hevy/WORKOUT_ID/report.md
   ```

   If the report has blocking Agent Next Actions, stop and summarize the blockers. Do not apply, except for the explicit required-template workflow in step 6.

6. Ensure required Hevy templates from the plan.

   First dry-run:

   ```bash
   uv run fitness-tracker hevy-templates ensure-from-plan reports/sync-review/truecoach-to-hevy/WORKOUT_ID/plan.json --dry-run
   ```

   If the dry-run is clean and templates need creating, run:

   ```bash
   uv run fitness-tracker hevy-templates ensure-from-plan reports/sync-review/truecoach-to-hevy/WORKOUT_ID/plan.json --yes
   ```

   If a Hevy template create returns HTTP 200/201 but local response parsing fails, do not retry the POST immediately. Verify remotely whether the template was created:

   ```bash
   uv run fitness-tracker hevy-templates find --title "Template Title"
   ```

   If it exists remotely, persist the discovered template ID locally and continue. This avoids duplicate custom templates.

   Then regenerate the review:

   ```bash
   uv run fitness-tracker sync-review truecoach-to-hevy --workout-id WORKOUT_ID --summary
   ```

7. Generate the exact Hevy request body without writing to Hevy.

   ```bash
   uv run fitness-tracker sync-apply truecoach-to-hevy --workout-id WORKOUT_ID --dry-run
   ```

   Inspect `reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.json` if needed.

8. If the generated dry-run fails from nuanced set parsing, prefer a manually reviewed one-off request body over broad parser/code changes unless the user explicitly asks to generalize the parser.

   Manual nuance examples:
   - Standalone distance target `5km - Under 09:55` may need one set with `distance_meters: 5000` and `duration_seconds: 595`.
   - Non-prescriptive recovery blocks such as `Down Regulate` may need a simple duration row.

   When manually adjusting a request:
   - Write it as `reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.manual.json`.
   - Verify no exercise has empty `sets`, using `jq` if useful.
   - Keep the manual changes scoped to the workout-specific nuance.

9. Before creating a routine, search Hevy for an existing routine with the exact generated title.

   ```bash
   uv run fitness-tracker hevy routines find --title $'DD Mon YYYY\nWorkout Title\nWORKOUT_ID'
   ```

   If one exists, ask the user whether to delete and recreate, update in place, or stop. Do not update in place by default. Prefer delete-and-recreate only after explicit confirmation.

10. Apply only if the dry-run or manually reviewed request succeeds and there are no blocking actions.

   For the standard path:

   ```bash
   uv run fitness-tracker sync-apply truecoach-to-hevy --workout-id WORKOUT_ID
   ```

   For a manual request body, create the routine from the reviewed JSON body. If the user chose delete-and-recreate, delete the existing routine first and then create fresh from the manual request.

   Delete an existing routine only with explicit user confirmation:

   ```bash
   uv run fitness-tracker hevy routines delete ROUTINE_ID --yes
   ```

   Create from the manual request:

   ```bash
   uv run fitness-tracker hevy routines create-from-json reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.manual.json
   ```

   Or use the sync apply manual-request wrapper:

   ```bash
   uv run fitness-tracker sync-apply truecoach-to-hevy --workout-id WORKOUT_ID --manual-request reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.manual.json
   ```

   Inspect the created routine after writing:

   ```bash
   uv run fitness-tracker hevy routines inspect ROUTINE_ID
   ```

11. Report the result.
   - List each processed True Coach Workout ID and title.
   - List any created Hevy template IDs.
   - List any deleted or created Hevy Routine IDs.
   - List generated report, plan, and Hevy request paths.
   - Mention any skipped rest days or blockers.
   - Mention any dirty runtime checkpoint files left in the working tree.
