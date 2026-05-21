# Hevy and True Coach Sync Workflow

This guide documents the automatic workflow started by `main.py`. The script is
small because the real workflow lives in `SyncService.run()` and its directional
syncers.

`main.py` does four things:

1. Loads runtime configuration from environment variables.
2. Creates the SQLAlchemy engine for the local tracker database.
3. Builds concrete sync dependencies with `SyncDeps.from_config()`.
4. Runs `SyncService.run()`.

## System roles

- True Coach is the Coach-authored prescription source.
- Hevy is the Athlete logging and performed-results source.
- Apple Health is an evidence source for local tracker metrics and workout
  timing context.
- The local tracker database is the bridge. It stores platform snapshots,
  cross-platform links, metric rows, set rows, and sync state.

Use the terms from `CONTEXT.md`: a Routine is a planned prescription, and a
Workout is a completed training session.

## Full sync order

`SyncService.run()` executes one full sync in this order:

1. Import Apple Health metrics and workouts into the local tracker.
2. Fetch recent True Coach Workouts from the True Coach API.
3. Persist those True Coach Workouts and Workout Items locally.
4. Read the Hevy workout-events checkpoint.
5. Fetch Hevy workout events since that checkpoint.
6. Sync updated or deleted Hevy Workouts into the local tracker.
7. For each updated Hevy Workout, run the strict Hevy-to-True-Coach Result sync
   workflow. Strict-safe plans apply through the review/apply path; plans with
   warnings or blockers write review artifacts without mutating True Coach.
8. Write the new Hevy checkpoint.
9. Push tracker assessment metrics to True Coach assessments.
10. Delete existing Hevy Routine drafts.
11. Fetch recent True Coach Workouts again.
12. Persist the fresh True Coach snapshot again.
13. Find True Coach Workouts due today or earlier.
14. Create a Hevy Routine for each due True Coach Workout.

The second True Coach fetch matters: earlier Hevy-to-True-Coach updates may have
changed remote Workout Item state, so Routine creation should use a fresh local
snapshot.

## Directional sync responsibilities

The service hides the individual syncers from callers, but the workflow depends
on these directional responsibilities:

- Apple Health to tracker imports health metrics and workout evidence from
  Dropbox.
- True Coach to tracker stores Coach-authored Workout and Workout Item
  snapshots locally.
- Hevy to tracker stores performed or deleted Hevy Workouts locally, extracts
  the True Coach Workout id from the Hevy Workout title, links matching tracker
  rows, and refreshes local performed set data.
- Hevy to True Coach Result sync writes review artifacts for performed Hevy
  Workouts, applies strict-safe result updates through the review/apply path,
  and marks the True Coach Workout completed only when the result workflow
  decides it is safe.
- Tracker to True Coach pushes local metric rows into True Coach assessments.
- True Coach to Hevy converts due True Coach Workouts into Hevy Routines.

## Hevy checkpoint behavior

The Hevy workout-events checkpoint controls incremental Hevy sync. The service
reads the previous checkpoint before fetching Hevy events, then writes the
current run timestamp after the event sync.

The default lower bound is `2025-01-01T00:00:00Z` when no checkpoint exists.

## Hevy Workout to True Coach result flow

When a Hevy updated-workout event is received:

1. The Hevy Workout is stored locally.
2. The syncer tries to parse the True Coach Workout id from the Hevy title.
3. If the local tracker has that True Coach Workout, the tracker row is linked
   to the Hevy Workout id and start/end timestamps.
4. Hevy exercise blocks are linked to True Coach Workout Items by deterministic
   SQL first, then LLM-assisted linking for remaining unmatched items.
5. Local tracker exercises and sets are updated from the linked Hevy rows.
6. The strict Result sync workflow writes `hevy-to-truecoach-results` review
   artifacts for the performed Hevy Workout.
7. If the plan has no warnings, item blockers, or decision blockers, the
   workflow applies the reviewed request to matching True Coach Workout Items
   and marks the True Coach Workout completed when safe.
8. If the plan has warnings or blockers, automatic sync leaves the review
   artifacts for an Agent and does not mutate True Coach.

The automatic Result sync path fails loudly on apply/API errors. It does not
preserve the legacy stale True Coach row repair-on-404 behavior.

## Agentic Hevy to True Coach review

The automatic path and Agentic path share the same review/apply workflow:

1. Generate a Hevy to True Coach result sync review for one Hevy Workout.
2. Show linked Hevy exercise blocks, matched True Coach Workout Items, proposed
   Coach-facing result text, skipped items, unsupported formatters, and whether
   the True Coach Workout can be marked completed.
3. Let the Agent review mappings and result text without inventing performed set
   outcomes that are not present in Hevy evidence.
4. Apply only a reviewed plan.

Unlinked, ambiguously linked, or unsupported performed Hevy items are blockers
by default. A reviewed partial apply may update confidently linked True Coach
Workout Items, but it must not mark the whole True Coach Workout completed while
known performed items remain unmapped.

Review artifacts should separate deterministic evidence from judgement:

- `report.md` summarizes the proposed sync for the Agent.
- `plan.json` records linked Hevy data, candidate True Coach targets, proposed
  result text, blockers, and warnings.
- `result-decisions.json` stores editable Agent decisions.
- `decision-validation.json` records blockers and warnings after decisions.
- `truecoach-update-request.json` records the exact True Coach mutations that
  apply would send.

The first Agentic implementation should target one explicit Hevy Workout id:

```bash
uv run fitness-tracker sync-review hevy-to-truecoach-results --workout-id HEVY_ID
uv run fitness-tracker sync-apply hevy-to-truecoach-results --workout-id HEVY_ID --decisions reports/sync-review/hevy-to-truecoach-results/HEVY_ID/result-decisions.json
```

Candidate discovery can be added later after the single-Workout review and
apply flow is reliable.

Appropriate Agent decisions include mapping overrides, explicit omissions with
reasons, readable result-text adjustments that preserve the same performed
values, partial-apply approval, and whether to mark the True Coach Workout
completed when all performed items are mapped.

The deterministic formatter remains responsible for set result text. The Agent
primarily reconciles Hevy exercise blocks with the intended True Coach Workout
Items. If the Athlete replaced an exercise during the Hevy Workout, the Agent
should map the performed Hevy item to the intended True Coach item and add an
item-scoped context line such as `Performed as: Chest Supported Row instead of
Seated Cable Row`. If the Athlete moved exercises around, the Agent should add
an item-scoped order note when the changed fatigue context is meaningful. These
context lines wrap the formatter output; they should not rewrite performed set
values.

Repeated Hevy exercise templates in the same Workout are not automatically
duplicates. They may represent different roles, especially warmup work followed
by main work. The Agent should use set type, load, position, nearby True Coach
items, notes, and the surrounding Workout structure to map repeated exercises.
If the role remains unclear, the affected items should stay blocked until the
Athlete answers.

The Agent should prompt the Athlete instead of deciding when:

- the same exercise is repeated and order plus sets/reps do not identify which
  True Coach item each block represents;
- a performed replacement could map to more than one True Coach Workout Item;
- applying would duplicate the same performed work into multiple True Coach
  items;
- a Hevy item would be omitted without a clear reason;
- completion status depends on a questionable mapping.

## True Coach to Hevy Routine flow

After Hevy results and assessments have been processed, the service plans due
True Coach Workouts through the Routine creation review workflow. It deletes
existing generated Hevy Routine drafts and recreates Routines only when every
due plan is strict-safe.

For each due Workout:

1. The review service writes `report.md` and `plan.json` under
   `reports/sync-review/truecoach-to-hevy/WORKOUT_ID`.
2. True Coach Workout Items are sorted by position.
3. The Workout order and superset groups are parsed from the True Coach short
   description when available.
4. Each Workout Item is mapped to a concrete Hevy exercise template through its
   True Coach exercise link, tracker mapping, deterministic template selection,
   or explicit override.
5. Sets are parsed from the True Coach prescription with deterministic planners.
6. Safety classification marks plans with warnings, blockers, placeholder
   templates, missing source markers, or non-deterministic set provenance as
   review-required.
7. If any due Workout requires review, no Hevy Routine drafts are deleted or
   created.
8. If every due Workout is strict-safe, the workflow writes `hevy-request.json`,
   creates the new Hevy Routines, records `hevy-response.json`, then deletes old
   generated Routine drafts marked with `RoutineBatch: truecoach-to-hevy`.

The retired direct Routine creator is no longer an automatic path. It raises a
deprecation error instead of using placeholders, LLM-derived set structures, or
direct Hevy Routine mutation.

## Agent review workflows

The automatic workflow explains what the production sync does. When an Agent is
asked to make a nuanced Hevy write, use the command recipes instead:

- Upcoming Coach prescription to Hevy Routine:
  `.agents/commands/create-hevy-routine.md`
- Historical completed True Coach Workout to logged Hevy Workout:
  `.agents/commands/tc-backfill-workout.md`

Those workflows generate review artifacts, expose blockers, and keep heuristic
judgement explicit before applying remote writes.

## Review workflow module shape

Review workflows in `fitness_tracker/sync_review/` follow the same module
shape even when they target different platform directions. The workflow shell
loads local source data, writes artifacts, renders reports, and coordinates
review versus apply commands. The domain planner builds deterministic plan data
from platform snapshots and local tracker rows. The decisions/request builder
validates editable decisions and converts a reviewed plan into an exact platform
request. The apply/mutation module is the only layer that performs remote
writes or local link repair.

Routine creation review is the True Coach prescription to Hevy Routine path.
`routine_prescription.py` plans Coach-authored Workout Items, mixed-mode
prescriptions, Athlete-history enrichment, template requirements, and
Split Circuit evidence. The review shell emits `plan.json`, `report.md`, and,
when apply is requested, `hevy-request.json`. The Hevy Routine request belongs
after review because numeric Hevy grouping, folder selection, and final request
shape are mutation concerns rather than source evidence.

Workout backfill review is historical performed-result transfer from a
completed True Coach Workout into a logged Hevy Workout.
`true_coach_workout_backfill.py` is the workflow shell,
`workout_backfill_performed_work.py` plans performed work, and
`workout_backfill_request.py` owns editable backfill decisions and the Hevy
Workout request shape. `workout_backfill_apply.py` performs platform mutation,
idempotency checks, remote repair, and local tracker link repair. Its artifacts
separate `plan.json`, `apple-health-evidence.json`,
`decisions.json`, `decision-validation.json`, and, after
`workout-backfill write-request`, `hevy-workout-request.json`.

Result sync review is the performed Hevy Workout to True Coach result path.
`hevy_to_true_coach_result.py` is the workflow shell,
`hevy_to_true_coach_result_planner.py` builds deterministic performed-item
mapping evidence, and `hevy_to_true_coach_result_decisions.py` owns editable
Agent decisions plus the `truecoach-update-request.json` apply request.
Result sync review artifacts include `plan.json`, `result-decisions.json`,
`decision-validation.json`, `truecoach-update-request.json`, and `report.md`.

Deterministic plan data is evidence: source Workout or Routine identifiers,
platform snapshot fields, parsed sets, Split Circuit plans, candidate mappings,
warnings, blockers, and proposed formatter output. Editable decision artifacts
record Agent or Athlete judgement: mapping overrides, selected timestamps,
explicit omissions, template choices, partial-apply approval, completion
approval, and readable context lines that preserve the same performed values.
Request artifacts are reviewed mutation payloads derived from plan plus
decisions; they should not be treated as the source audit trail.

Apply modules perform platform mutations only after validation. They may define
small writer seams for the specific platform operation they execute, such as
creating one Hevy Workout or updating True Coach Workout Items, so tests and
dry runs can verify the reviewed request. Those review apply mutation seams are
not a reintroduction of broad sync-layer port wiring; the automatic sync layer
still follows `docs/adr/0002-sync-layer-uses-concrete-wiring.md`.

## Platform primitive commands

A platform primitive command performs one explicit operation against a single
third-party platform or the local cache, without cross-platform judgement.

Use platform primitive commands for focused inspection, discovery, and explicit
single-platform writes. Keep nuanced cross-platform behaviour in `sync-review`
and `sync-apply`, where review artifacts can separate deterministic evidence
from Agent judgement.

Platform primitive command conventions:

- Commands live under the `fitness-tracker truecoach ...` and
  `fitness-tracker hevy ...` namespaces.
- Resource-first command groups are preferred, such as `workouts inspect`,
  `workout-items update-result`, `routines inspect`, and
  `exercise-templates find`.
- Hevy exercise template commands live under
  `fitness-tracker hevy exercise-templates ...`.
- For commands that expose `--json`, the --json stdout is machine-only: it must
  be a single strict JSON document. Human-facing warnings and progress messages
  go to stderr so Agents can parse stdout without filtering.
- Platform inspection is remote-first: `inspect`, `list`, and `find` commands
  read remote API truth by default. Local tracker reads must use explicit
  `cached` commands.
- Create and update commands should make mutation obvious in the command name,
  accept structured request input where practical, and write response artifacts
  when requested.
- Destructive commands should require an explicit confirmation flag such as
  `--yes`.
- Nuanced cross-platform judgement belongs in `sync-review` and `sync-apply`,
  not in platform primitive commands.
- Removed legacy command groups should not be used in Agent docs or command
  recipes.

### Implemented platform primitive surface

These commands are implemented and should be preferred in Agent workflows.

True Coach Workouts:

```bash
fitness-tracker truecoach workouts list --state pending --limit 20 --json
fitness-tracker truecoach workouts inspect --workout-id WORKOUT_ID --json
fitness-tracker truecoach workouts inspect --workout-id WORKOUT_ID --json --raw
fitness-tracker truecoach workouts cached --workout-id WORKOUT_ID --json
fitness-tracker truecoach workouts due --date YYYY-MM-DD --json
fitness-tracker truecoach workouts import-recent --pages 2 --json
```

True Coach Workout Items:

```bash
fitness-tracker truecoach workout-items inspect --item-id ITEM_ID --json
fitness-tracker truecoach workout-items inspect --item-id ITEM_ID --json --raw
fitness-tracker truecoach workout-items update-result --request REQUEST.json --dry-run --json
fitness-tracker truecoach workout-items update-result --request REQUEST.json --yes --json
fitness-tracker truecoach workout-items update-result --item-id ITEM_ID --text-file result.txt --dry-run --json
fitness-tracker truecoach workout-items update-result --item-id ITEM_ID --text-file result.txt --yes --json
```

Hevy Workouts:

```bash
fitness-tracker hevy workouts inspect WORKOUT_ID --json
fitness-tracker hevy workouts inspect WORKOUT_ID --json --raw
fitness-tracker hevy workouts cached WORKOUT_ID --json
```

Hevy Routines:

```bash
fitness-tracker hevy routines find --title "Routine Title" --json
fitness-tracker hevy routines inspect ROUTINE_ID --json
fitness-tracker hevy routines inspect ROUTINE_ID --json --raw
fitness-tracker hevy routines create-from-json request.json --response-path response.json --json
fitness-tracker hevy routines update-from-json ROUTINE_ID request.json --response-path response.json --json
fitness-tracker hevy routines delete ROUTINE_ID --yes --json
fitness-tracker hevy routines diff-json ROUTINE_ID request.json --output-path diff.md
```

Hevy Routine Folders:

```bash
fitness-tracker hevy routine-folders ensure --title "True Coach" --json
```

Hevy Exercise Templates:

```bash
fitness-tracker hevy exercise-templates find --title "Template Title" --json
fitness-tracker hevy exercise-templates fuzzy-find --title "Template Title" --limit 10 --json
fitness-tracker hevy exercise-templates create \
  --title "Template Title" \
  --type weight_reps \
  --equipment other \
  --muscle-group full_body \
  --dry-run \
  --json
fitness-tracker hevy exercise-templates create \
  --title "Template Title" \
  --type weight_reps \
  --equipment other \
  --muscle-group full_body \
  --yes \
  --json
fitness-tracker hevy exercise-templates ensure-from-plan PLAN.json --dry-run --json
fitness-tracker hevy exercise-templates ensure-from-plan PLAN.json --yes --json
```

Exercise Links:

```bash
fitness-tracker exercise-links set \
  --truecoach-exercise-id TRUECOACH_EXERCISE_ID \
  --hevy-template-id HEVY_TEMPLATE_ID
```

### Future intended platform primitive surface

These command shapes are intended but not implemented yet. Do not use them in
Agent command recipes until `fitness-tracker --help` shows them.

Exercise Links:

```bash
fitness-tracker exercise-links inspect --truecoach-exercise-id TRUECOACH_EXERCISE_ID --json
fitness-tracker exercise-links find-unlinked --json
```
