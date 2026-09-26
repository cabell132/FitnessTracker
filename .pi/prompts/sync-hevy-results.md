---
description: Incrementally sync completed Hevy Workout results to True Coach through the Hevy events API
argument-hint: "[HEVY_WORKOUT_ID]"
---

# Sync Hevy Results To True Coach

Incrementally sync completed Hevy Workout performed results to matching True
Coach Workouts. By default, this command uses the Hevy workout-events API and
the database checkpoint `hevy.workout_events` so already-processed Hevy updates
are not replayed forever.

## Usage

`/sync-hevy-results [HEVY_WORKOUT_ID]`

- No argument: preferred path. Read the DB checkpoint, fetch Hevy workout events
  since that watermark, persist each event, run Result sync, and advance the DB
  checkpoint after each successfully persisted event.
- `HEVY_WORKOUT_ID`: targeted repair/review path for one known Workout id. This
  does **not** discover via events or advance the checkpoint; use only when the
  incremental path has already surfaced a review artifact or the user explicitly
  wants one Workout.

The explicit argument must be the Hevy API Workout id, usually a UUID stored
locally in `HevyAppWorkout.id`. A public/share id may not work with the Hevy API.

## Checkpoint semantics

Use the project sync rules from `docs/agents/hevy-truecoach-workflow.md`:

- checkpoint key: `hevy.workout_events`;
- stored in the database via `SyncCheckpoint`, seeded from legacy file state only
  when the DB row is missing;
- default lower bound: `2025-01-01T00:00:00Z`;
- apply the configured five-minute overlap when reading an existing checkpoint;
- advance from Hevy source timestamps only after successful event persistence:
  - updated Workout: `workout.updated_at`;
  - deleted Workout: `deleted_at`;
- Result sync review/apply failures must not roll back an already-persisted Hevy
  event checkpoint.

## Workflow: incremental events path

1. Check the working tree.

   ```bash
   git status --short --branch
   ```

   Do not revert unrelated user changes. Runtime report/checkpoint files may be
   dirty; mention them if present.

2. If no `HEVY_WORKOUT_ID` argument was provided, run the checkpoint preflight
   before any Hevy fetch or True Coach write. This query must not call
   `deps.checkpoints.read(...)`, because that can seed a missing DB row from the
   legacy file and hide the fact that the run would replay a large history.

   ```bash
   npm run env:run -- uv run python - <<'PY'
   import json
   from datetime import UTC, datetime, timedelta
   from pathlib import Path

   from sqlalchemy import create_engine, text

   from fitness_tracker.config import Config
   from fitness_tracker.sync.adapters.database_checkpoint_store import DEFAULT_OVERLAP_SECONDS
   from fitness_tracker.sync.adapters.file_checkpoint_store import (
       HEVY_CHECKPOINT_KEY,
       HEVY_WORKOUT_EVENTS_CHECKPOINT_KEY,
   )

   cfg = Config.from_env()
   default = datetime(2025, 1, 1, tzinfo=UTC)
   engine = create_engine(cfg.database_url)

   with engine.connect() as conn:
       row = conn.execute(
           text('select source_watermark_at, overlap_seconds, updated_at from "SyncCheckpoint" where key = :key'),
           {"key": HEVY_WORKOUT_EVENTS_CHECKPOINT_KEY},
       ).fetchone()

   legacy_value = None
   legacy_path = Path("sync_checkpoints.json")
   if legacy_path.exists():
       data = json.loads(legacy_path.read_text())
       raw = data.get(HEVY_CHECKPOINT_KEY) or data.get(HEVY_WORKOUT_EVENTS_CHECKPOINT_KEY)
       if raw:
           legacy_value = datetime.fromisoformat(raw)
           if legacy_value.tzinfo is None:
               legacy_value = legacy_value.replace(tzinfo=UTC)
           else:
               legacy_value = legacy_value.astimezone(UTC)

   if row is None:
       print("checkpoint_db_row=missing")
       print(f"legacy_seed_candidate={legacy_value.isoformat() if legacy_value else 'none'}")
       print(f"default_candidate={default.isoformat()}")
       raise SystemExit(
           "STOP: DB checkpoint row is missing. Do not run incremental sync until the user confirms the seed/window."
       )

   previous = row.source_watermark_at
   if previous.tzinfo is None:
       previous = previous.replace(tzinfo=UTC)
   else:
       previous = previous.astimezone(UTC)
   overlap_seconds = row.overlap_seconds or DEFAULT_OVERLAP_SECONDS
   since = previous - timedelta(seconds=overlap_seconds)
   now = datetime.now(UTC)

   print("checkpoint_db_row=present")
   print(f"checkpoint_before={previous.isoformat()}")
   print(f"checkpoint_updated_at={row.updated_at.isoformat() if row.updated_at else 'unknown'}")
   print(f"checkpoint_overlap_seconds={overlap_seconds}")
   print(f"events_since={since.isoformat()}")
   print(f"window_seconds={(now - since).total_seconds():.0f}")

   if now - since > timedelta(hours=24):
       raise SystemExit(
           "STOP: proposed Hevy events window is older than 24 hours. Ask the user to confirm before running the mutating sync."
       )
   PY
   ```

3. Only after the preflight passes, run the incremental Hevy events sync. This
   uses the app's production wiring, including the DB-backed checkpoint store.
   Paste/run the heredoc exactly as shown, with no leading spaces inside the
   Python body.

   ```bash
   npm run env:run -- uv run python - <<'PY'
   from datetime import UTC, datetime, timedelta

   from sqlalchemy import create_engine

   from fitness_tracker.config import Config
   from fitness_tracker.sync import SyncDeps, SyncService
   from fitness_tracker.sync.adapters.database_checkpoint_store import DEFAULT_OVERLAP_SECONDS
   from fitness_tracker.sync.adapters.file_checkpoint_store import HEVY_WORKOUT_EVENTS_CHECKPOINT_KEY

   cfg = Config.from_env()
   deps = SyncDeps.from_config(create_engine(cfg.database_url), cfg)
   service = SyncService(deps)

   default = datetime(2025, 1, 1, tzinfo=UTC)
   previous = deps.checkpoints.read(HEVY_WORKOUT_EVENTS_CHECKPOINT_KEY, default)
   since = previous if previous == default else previous - timedelta(seconds=DEFAULT_OVERLAP_SECONDS)

   print(f"checkpoint_before={previous.isoformat()}")
   print(f"events_since={since.isoformat()}")

   events = service.sync_hevy_workouts(since=since)
   print(f"event_count={len(events)}")
   for event in events:
       if event.type == "updated":
           print(f"updated workout_id={event.workout.id} updated_at={event.workout.updated_at}")
       elif event.type == "deleted":
           print(f"deleted workout_id={event.id} deleted_at={event.deleted_at}")

   after = deps.checkpoints.read(HEVY_WORKOUT_EVENTS_CHECKPOINT_KEY, default)
   print(f"checkpoint_after={after.isoformat()}")
   PY
   ```

4. Inspect any review-required artifacts created by automatic Result sync.

   ```bash
   find reports/sync-review/hevy-to-truecoach-results -maxdepth 2 -name report.md -print | sort
   ```

   For any Workout needing judgement, continue with the targeted review path
   below using that Hevy Workout id.

5. Report the incremental result.

   Include:

   - checkpoint preflight status, including whether the DB checkpoint row was
     present;
   - checkpoint before/after;
   - events query lower bound;
   - count of updated/deleted events;
   - updated Hevy Workout ids synced;
   - any review-required artifact directories;
   - any errors or dirty files left in the working tree.

## Workflow: targeted one-Workout review/apply path

Use this path only when an explicit `HEVY_WORKOUT_ID` is provided or an
incremental run produced a review artifact that needs Agent decisions.

1. Resolve `$ARGUMENTS` to a single Hevy Workout id.
   - Echo the resolved id before doing True Coach writes.
   - If no id is provided, use the incremental events path instead of asking for
     an id.

2. Generate the Result sync review.

   ```bash
   npm run env:run -- uv run fitness-tracker sync-review hevy-to-truecoach-results --workout-id HEVY_WORKOUT_ID
   ```

   If the command says the Hevy Workout is missing from the local DB, confirm the
   id remotely before continuing:

   ```bash
   npm run env:run -- uv run fitness-tracker hevy workouts inspect HEVY_WORKOUT_ID
   ```

   If remote inspect returns `404`, stop and ask for the correct Hevy API
   Workout id. Do not manually advance the checkpoint from this targeted path.

3. Inspect the generated artifacts.

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

4. If the review reports a missing True Coach Workout link, check whether the
   True Coach id is embedded in the Hevy Workout title and already exists
   locally.

   ```bash
   npm run env:run -- uv run fitness-tracker truecoach workouts import-recent --pages 2 --per-page 20
   ```

   If both platform snapshots exist locally but the tracker bridge row is
   missing, repair local tracker links before reviewing again. Do not apply
   while the review still says `Missing True Coach Workout link for Hevy
   Workout`.

5. Make Agent mapping decisions only where judgement is needed.

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

6. Regenerate the review with decisions.

   ```bash
   npm run env:run -- uv run fitness-tracker sync-review hevy-to-truecoach-results \
     --workout-id HEVY_WORKOUT_ID \
     --decisions reports/sync-review/hevy-to-truecoach-results/HEVY_WORKOUT_ID/result-decisions.json
   ```

   Continue only when `blockers: 0`.

7. Run dry-run apply and inspect the exact True Coach request.

   ```bash
   npm run env:run -- uv run fitness-tracker sync-apply hevy-to-truecoach-results \
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

8. Apply only after dry-run is clean.

   ```bash
   npm run env:run -- uv run fitness-tracker sync-apply hevy-to-truecoach-results \
     --workout-id HEVY_WORKOUT_ID \
     --decisions reports/sync-review/hevy-to-truecoach-results/HEVY_WORKOUT_ID/result-decisions.json \
     --yes
   ```

9. Verify True Coach after apply.

   Refresh local True Coach data:

   ```bash
   npm run env:run -- uv run fitness-tracker truecoach workouts import-recent --pages 2 --per-page 20
   ```

   Check that:

   - the True Coach Workout is completed when completion was approved;
   - each intended True Coach Workout Item is completed;
   - result text contains performed results, not redundant exercise names;
   - any intended omissions or unresolved items are reported.

10. Report the result.

    Include:

    - Hevy Workout id;
    - True Coach Workout id and title;
    - count of updated True Coach Workout Items;
    - whether the True Coach Workout was marked completed;
    - mapping overrides, omissions, partial apply, and completion decision;
    - paths to report, decisions, validation, and update request artifacts;
    - note that targeted review/apply did not advance the DB checkpoint;
    - any dirty files left in the working tree.
