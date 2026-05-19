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

3. Refresh recent True Coach API data before trusting the configured database.

   ```bash
   uv run fitness-tracker truecoach workouts import-recent --pages 2 --per-page 20 --json
   ```

   This command persists recent True Coach Workouts and Workout Items locally. If the
   import fails, stop and report the API/import failure instead of continuing from a
   stale DB snapshot.

4. Find True Coach Workouts due on that date from the configured database.

   ```bash
   uv run fitness-tracker truecoach workouts due --date YYYY-MM-DD --json
   ```

   If no rows are found, stop and report that the configured DB has no True Coach Workouts due on that date.

5. For each non-rest-day workout, generate a sync review.

   ```bash
   uv run fitness-tracker sync-review truecoach-to-hevy --workout-id WORKOUT_ID --summary
   ```

6. Inspect the report and plan.

   ```bash
   sed -n '1,260p' reports/sync-review/truecoach-to-hevy/WORKOUT_ID/report.md
   ```

   If the report has blocking Agent Next Actions, stop and summarize the blockers. Do not apply, except for the explicit required-template workflow in step 6.

7. Resolve missing Hevy template mappings before creating new templates.

   For each missing mapping or likely template gap, fuzzy-search remote Hevy first:

   ```bash
   uv run fitness-tracker hevy exercise-templates fuzzy-find --title "Template Title" --limit 10 --json
   ```

   If a suitable Hevy template already exists, persist the True Coach to Hevy exercise
   join-table link explicitly:

   ```bash
   uv run fitness-tracker exercise-links set \
     --truecoach-exercise-id TRUECOACH_EXERCISE_ID \
     --hevy-template-id HEVY_TEMPLATE_ID
   ```

   Use `CONTEXT.md` terms when reasoning:
   - A permanent exercise link is broad and affects future matching by True Coach exercise id.
   - A Template selection override is narrower and may be better when Coach notes materially
     change the movement.
   - Exercise replacements made during a Hevy Workout can drop notes and pull set values
     from history; do not silently treat dropped notes or load changes as Athlete intent.

8. Ensure required Hevy templates from the plan only after fuzzy search.

   First dry-run:

   ```bash
   uv run fitness-tracker hevy exercise-templates ensure-from-plan reports/sync-review/truecoach-to-hevy/WORKOUT_ID/plan.json --dry-run --json
   ```

   If the dry-run is clean and templates need creating, run:

   ```bash
   uv run fitness-tracker hevy exercise-templates ensure-from-plan reports/sync-review/truecoach-to-hevy/WORKOUT_ID/plan.json --yes --json
   ```

   If a Hevy template create returns HTTP 200/201 but local response parsing fails, do not retry the POST immediately. Verify remotely whether the template was created:

   ```bash
   uv run fitness-tracker hevy exercise-templates fuzzy-find --title "Template Title" --limit 10 --json
   ```

   If it exists remotely, persist the discovered template ID locally with
   `exercise-links set` and continue. This avoids duplicate custom templates.

   Then regenerate the review:

   ```bash
   uv run fitness-tracker sync-review truecoach-to-hevy --workout-id WORKOUT_ID --summary
   ```

9. Ensure a Hevy routine folder.

   Hevy may reject routine creation when `folder_id` is missing. Reuse or create a
   routine folder before writing:

   ```bash
   uv run fitness-tracker hevy routine-folders ensure --title "True Coach" --json
   ```

   Keep the returned folder id for the apply command.

10. Generate the exact Hevy request body without writing to Hevy.

   ```bash
   uv run fitness-tracker sync-apply truecoach-to-hevy --workout-id WORKOUT_ID --dry-run --folder-id FOLDER_ID
   ```

   Inspect `reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.json` if needed.

11. Handle known request nuances with explicit CLI flags before editing JSON by hand.

   For non-prescriptive recovery blocks such as `Down Regulate`, prefer:

   ```bash
   uv run fitness-tracker sync-apply truecoach-to-hevy \
     --workout-id WORKOUT_ID \
     --down-regulate-duration 300 \
     --folder-id FOLDER_ID \
     --dry-run
   ```

   Meter prescriptions such as `5 x 400m` must produce `distance_meters: 400`, not
   `reps: 400`. Length shorthand `L` means 10m, so `10 x 1L` means ten 10m sets.

12. If the generated dry-run still fails from nuanced set parsing, prefer a manually reviewed one-off request body over broad parser/code changes unless the user explicitly asks to generalize the parser.

   Manual nuance examples:
   - Standalone distance target `5km - Under 09:55` may need one set with `distance_meters: 5000` and `duration_seconds: 595`.

   When manually adjusting a request:
   - Write it as `reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.manual.json`.
   - Verify no exercise has empty `sets`, using `jq` if useful.
   - Keep the manual changes scoped to the workout-specific nuance.

13. Before creating a routine, search Hevy for an existing routine with the exact generated title.

   ```bash
   uv run fitness-tracker hevy routines find --title $'DD Mon YYYY\nWorkout Title\nWORKOUT_ID' --json
   ```

   If one exists, ask the user whether to delete and recreate, update in place, or stop. Do not update in place by default. Prefer delete-and-recreate only after explicit confirmation.

14. Apply only if the dry-run or manually reviewed request succeeds and there are no blocking actions.

   For the standard path:

   ```bash
   uv run fitness-tracker sync-apply truecoach-to-hevy --workout-id WORKOUT_ID --folder-id FOLDER_ID
   ```

   For a patched known-nuance path:

   ```bash
   uv run fitness-tracker sync-apply truecoach-to-hevy \
     --workout-id WORKOUT_ID \
     --down-regulate-duration 300 \
     --folder-id FOLDER_ID
   ```

   For a manual request body, create the routine from the reviewed JSON body. If the user chose delete-and-recreate, delete the existing routine first and then create fresh from the manual request.

   Delete an existing routine only with explicit user confirmation:

   ```bash
   uv run fitness-tracker hevy routines delete ROUTINE_ID --yes --json
   ```

   Create from the manual request:

   ```bash
   uv run fitness-tracker hevy routines create-from-json reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.manual.json --json
   ```

   Or use the sync apply manual-request wrapper:

   ```bash
   uv run fitness-tracker sync-apply truecoach-to-hevy --workout-id WORKOUT_ID --manual-request reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.manual.json
   ```

   Inspect the created routine after writing:

   ```bash
   uv run fitness-tracker hevy routines inspect ROUTINE_ID --json
   ```

15. If the Athlete completes the Routine and updates it in Hevy, generate a Routine feedback diff.

   ```bash
   uv run fitness-tracker hevy routines diff-json ROUTINE_ID \
     reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-request.json \
     --output-path reports/sync-review/truecoach-to-hevy/WORKOUT_ID/hevy-routine-diff.md
   ```

   Use `--include-low-signal` only when you need to inspect performed-result noise.
   Follow `CONTEXT.md` and `docs/adr/0005-routine-feedback-diff-is-classified-by-signal.md`:
   - High-signal Routine feedback: template changes, rest period changes, notes changes,
     set-count changes, set-type changes.
   - Low-signal by default: pure load changes, pure rep changes, performed cardio
     durations on distance sets.
   - Rest period feedback may become a reusable default for the selected Hevy exercise
     template when Coach text is silent.
   - Explicit Coach rest text, such as `45s rest`, should be structured and takes
     priority over Athlete feedback.
   - Note-driven exercise replacement decisions are case-by-case Athlete decisions;
     do not silently update permanent links or overrides.

16. Report the result.
   - List each processed True Coach Workout ID and title.
   - List any created Hevy template IDs.
   - List any exercise-link mappings created or changed.
   - List the routine folder id used.
   - List any deleted or created Hevy Routine IDs.
   - List generated report, plan, Hevy request, and Routine feedback diff paths.
   - Mention any skipped rest days or blockers.
   - Mention any dirty runtime checkpoint files left in the working tree.
