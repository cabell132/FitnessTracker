# Sync Hevy Results To True Coach

Review and apply one completed Hevy Workout's performed results to the matching
True Coach Workout.

## Usage

`/sync-hevy-results HEVY_WORKOUT_ID`

The argument must be the Hevy API Workout id, usually a UUID stored locally in
`HevyAppWorkout.id`. A public/share id may not work with the Hevy API.

## Workflow

1. Resolve `$ARGUMENTS` to a single Hevy Workout id.
   - Echo the resolved id before doing True Coach writes.
   - If no id is provided, ask for the Hevy Workout id.

2. Check the working tree.

   ```bash
   git status --short --branch
   ```

   Do not revert unrelated user changes. Runtime report files may be dirty;
   mention them if present.

3. Generate the Result sync review.

   ```bash
   uv run fitness-tracker sync-review hevy-to-truecoach-results --workout-id HEVY_WORKOUT_ID
   ```

   If the command says the Hevy Workout is missing from the local DB, confirm the
   id remotely before continuing:

   ```bash
   uv run fitness-tracker hevy workouts inspect HEVY_WORKOUT_ID
   ```

   If remote inspect returns `404`, stop and ask for the correct Hevy API
   Workout id.

4. Inspect the generated artifacts.

   ```bash
   sed -n '1,260p' reports/sync-review/hevy-to-truecoach-results/HEVY_WORKOUT_ID/report.md
   jq . reports/sync-review/hevy-to-truecoach-results/HEVY_WORKOUT_ID/decision-validation.json
   ```

   The key files are:

   - `report.md`
   - `plan.json`
   - `result-decisions.json`
   - `decision-validation.json`
   - `truecoach-update-request.json` after dry-run/apply

5. If the review reports a missing True Coach Workout link, check whether the
   True Coach id is embedded in the Hevy Workout title and already exists
   locally.

   ```bash
   uv run fitness-tracker truecoach workouts import-recent --pages 2 --per-page 20
   ```

   If both platform snapshots exist locally but the tracker bridge row is
   missing, repair local tracker links before reviewing again. Do not apply
   while the review still says `Missing True Coach Workout link for Hevy
   Workout`.

6. Make Agent mapping decisions only where judgement is needed.

   Edit:

   ```bash
   reports/sync-review/hevy-to-truecoach-results/HEVY_WORKOUT_ID/result-decisions.json
   ```

   Appropriate decisions:

   - set `override_true_coach_workout_item_id` when a Hevy item clearly maps to
     a specific True Coach Workout Item;
   - set `action: "omit"` only with a clear `omit_reason`;
   - set `order_context` when a meaningful order change affects fatigue context;
   - set `allow_partial_apply: true` only when unresolved performed items should
     remain unsynced for now;
   - set `approve_completion: true` when all performed Hevy items are resolved
     and the True Coach Workout should be marked completed.

   Result text should normally contain performed results only. Do not add the
   exercise name to result text. Use `performed_as` only when the replacement is
   meaningfully different enough that the Coach needs to see the substitution.
   If the names are close enough, prefer a mapping override without
   `performed_as`.

7. Regenerate the review with decisions.

   ```bash
   uv run fitness-tracker sync-review hevy-to-truecoach-results \
     --workout-id HEVY_WORKOUT_ID \
     --decisions reports/sync-review/hevy-to-truecoach-results/HEVY_WORKOUT_ID/result-decisions.json
   ```

   Continue only when `blockers: 0`.

8. Run dry-run apply and inspect the exact True Coach request.

   ```bash
   uv run fitness-tracker sync-apply hevy-to-truecoach-results \
     --workout-id HEVY_WORKOUT_ID \
     --decisions reports/sync-review/hevy-to-truecoach-results/HEVY_WORKOUT_ID/result-decisions.json \
     --dry-run
   ```

   Inspect important request details:

   ```bash
   jq '{completion_status, mark_workout_completed, unresolved_hevy_workout_item_ids, omitted_hevy_workout_item_ids}' \
     reports/sync-review/hevy-to-truecoach-results/HEVY_WORKOUT_ID/truecoach-update-request.json
   ```

   If all performed Hevy items are resolved, `approve_completion` should normally
   be `true` and dry-run should show `completion_status: "performed"`.

9. Apply only after dry-run is clean.

   ```bash
   uv run fitness-tracker sync-apply hevy-to-truecoach-results \
     --workout-id HEVY_WORKOUT_ID \
     --decisions reports/sync-review/hevy-to-truecoach-results/HEVY_WORKOUT_ID/result-decisions.json \
     --yes
   ```

10. Verify True Coach after apply.

   Refresh local True Coach data:

   ```bash
   uv run fitness-tracker truecoach workouts import-recent --pages 2 --per-page 20
   ```

   Check that:

   - the True Coach Workout is completed when completion was approved;
   - each intended True Coach Workout Item is completed;
   - result text contains performed results, not redundant exercise names;
   - any intended omissions or unresolved items are reported.

11. Report the result.

   Include:

   - Hevy Workout id;
   - True Coach Workout id and title;
   - count of updated True Coach Workout Items;
   - whether the True Coach Workout was marked completed;
   - mapping overrides, omissions, partial apply, and completion decision;
   - paths to report, decisions, validation, and update request artifacts;
   - any dirty files left in the working tree.
