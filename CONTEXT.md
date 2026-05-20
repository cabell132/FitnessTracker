# Code Context

## Files Retrieved
1. `CONTEXT.md` (lines 1-200) - domain vocabulary and workflow constraints around Routine, Workout, backfill, result sync, feedback, split circuits, and review artifacts.
2. `docs/adr/0002-sync-layer-uses-concrete-wiring.md` (lines 1-15) - decision against broad ports/adapters in sync layer; deletion guidance.
3. `docs/adr/0003-workout-backfill-uses-review-artifacts-and-agent-decisions.md` (lines 1-35) - backfill review/apply/idempotency constraints.
4. `docs/adr/0004-circuits-sync-as-superset-routine-blocks.md` (lines 1-46) - circuit semantics, backfill requirements, and synthetic tracker row expectations.
5. `docs/adr/0006-hevy-to-truecoach-result-sync-uses-review-artifacts.md` (lines 1-8) - result sync must use review/apply artifacts for brittle mappings.
6. `docs/adr/0007-split-circuit-planning-uses-shared-review-core.md` (lines 1-22) - shared split-circuit core and workflow-adapter boundary.
7. `fitness_tracker/sync/_service.py` (lines 70-175) - full automatic sync pipeline and calls into legacy directional syncers.
8. `fitness_tracker/sync/true_coach_hevy/sync.py` (lines 47-138) - legacy direct True Coach to Hevy Routine creation orchestration.
9. `fitness_tracker/sync/hevy_true_coach/sync.py` (lines 40-140) - legacy direct Hevy result to True Coach mutation path.
10. `fitness_tracker/sync_review/true_coach_to_hevy.py` (lines 75-158, 241-320) - review/apply service and request builder for Routine creation.
11. `fitness_tracker/sync_review/routine_prescription.py` (lines 163-238, 255-428) - large Routine prescription planner, template selection, mixed-mode and circuit adaptation.
12. `fitness_tracker/sync_review/workout_backfill_performed_work.py` (lines 133-220, 295-420) - backfill performed-work planner and split-circuit adaptation.
13. `fitness_tracker/sync_review/workout_backfill_request.py` (lines 103-205) - backfill request builder and apply blockers over plan/decisions dicts.
14. `fitness_tracker/sync_review/hevy_to_true_coach_result.py` (lines 73-220) - result sync review/apply service.
15. `fitness_tracker/sync_review/hevy_to_true_coach_result_planner.py` (lines 22-131) - result mapping planner.
16. `fitness_tracker/sync/ports/hevy_workout_writer.py` (lines 1-49) and `fitness_tracker/sync/adapters/hevy_workout_writer.py` (lines 1-64) - representative shallow port/adapter pair.
17. `fitness_tracker/cli.py` (lines 90-172, 438-610, 1769-1928) - large CLI dispatcher/parser and review/apply orchestration branches.

## Key Code

- `SyncService.run()` calls `_execute_full_sync()`, which imports Apple Health, syncs True Coach, syncs Hevy events, writes checkpoints, syncs assessments, clears routines, re-syncs True Coach, then creates Hevy routines for due workouts (`fitness_tracker/sync/_service.py` lines 85-121). `sync_hevy_workouts()` immediately cascades updated Hevy workouts to the direct True Coach syncer (`fitness_tracker/sync/_service.py` lines 161-175).

- Legacy Routine creation is a single orchestration method with template lookup, placeholder allocation, superset extraction, LLM/deterministic set parsing, request creation, remote mutation, and cross-domain linking in one Module (`fitness_tracker/sync/true_coach_hevy/sync.py` lines 47-138). It does not write review artifacts.

- The review path is a separate Module: `TrueCoachToHevyReviewService.write_review()` builds plan/report artifacts, `write_apply_request()` rebuilds a typed Hevy request from `plan.json`, and `apply()` calls a writer (`fitness_tracker/sync_review/true_coach_to_hevy.py` lines 75-158). `_build_hevy_routine_request()` validates blockers and converts the plan dict into request models (`fitness_tracker/sync_review/true_coach_to_hevy.py` lines 241-320).

- `RoutinePrescriptionPlanner.review_item()` mixes template selection, required-template override resolution, circuit parsing, mixed-mode splitting, Athlete-history enrichment, warnings, and blockers (`fitness_tracker/sync_review/routine_prescription.py` lines 163-238). Its circuit adapter nests a template resolver and maps shared split-circuit plan data back into Routine-specific `PlannedBlock` objects (`fitness_tracker/sync_review/routine_prescription.py` lines 317-428).

- Backfill has a parallel but different adapter: `_circuit_plan_items()` expands split-circuit exercises, applies performed evidence, omissions/replacements, blockers, candidate IDs, notes, and per-movement sets (`fitness_tracker/sync_review/workout_backfill_performed_work.py` lines 320-405). Request eligibility and blocker logic is later recalculated over plain dicts in `workout_backfill_request.py` lines 143-180.

- ADR 0002 explicitly says broad sync `ports/` and `adapters/` were tried and reverted, with only checkpoint storage intended as live exception (`docs/adr/0002-sync-layer-uses-concrete-wiring.md` lines 6-15). Current usage still imports writer ports from `sync.ports` in review Modules, and representative `HevyWorkoutWriterAdapter` is a shallow pass-through except for remote idempotency search (`fitness_tracker/sync/adapters/hevy_workout_writer.py` lines 24-64).

## Architecture

The repo has two overlapping sync architectures:

1. **Automatic directional sync Modules** under `fitness_tracker/sync/`. `SyncService` wires concrete Implementations and hides step ordering. Directional syncers directly combine local DB access, API calls, parsing/formatting, and mutation.
2. **Review/apply workflow Modules** under `fitness_tracker/sync_review/`. These create durable artifacts (`plan.json`, request JSON, decisions JSON, reports), then apply through narrow writer seams.

The deeper domain vocabulary in `CONTEXT.md` and ADRs favors review artifacts for ambiguous Workouts, Routine backfill, split circuits, and result sync decisions. The friction is that several Seams are still encoded as ad-hoc dict shapes and large orchestration functions rather than as stable workflow concepts, while some shallow Interface/Adapter layers remain from an ADR-rejected experiment.

## Start Here

Start with `fitness_tracker/sync/_service.py`. It shows where automatic sync still enters legacy direct-mutation Implementations, which is the highest-leverage place to decide whether review/apply workflows should replace or be explicitly kept separate from automatic sync.

## Architectural Deepening Candidates

1. **Unify or retire the legacy direct Routine creation path**
   - **Files:** `fitness_tracker/sync/_service.py` lines 85-121; `fitness_tracker/sync/true_coach_hevy/sync.py` lines 47-138; `fitness_tracker/sync_review/true_coach_to_hevy.py` lines 75-158 and 241-320.
   - **Problem:** Two Modules implement True Coach -> Hevy Routine creation with different depth. The legacy Implementation is shallow at the seam but deep inside one method: it directly mutates Hevy, uses placeholder templates, sets `rest_seconds=0`, mixes LLM parsing with fallback parsing, and bypasses review blockers. The review Module has better Locality for artifacts and safety, but automatic `SyncService` still calls the legacy path.
   - **Deletion test:** If `fitness_tracker/sync/true_coach_hevy/sync.py` disappeared, the review/apply path still knows how to plan and create Routines, but `SyncService.create_hevy_routine()` would need a replacement policy. That indicates duplicate capability, not a necessary Adapter.
   - **Solution sketch:** Make one Routine creation Implementation authoritative. Either route automatic Routine creation through the review planner with an explicit no-review policy for safe cases, or explicitly mark the legacy syncer as a constrained fast path and strip duplicated parsing/planning logic from it.
   - **Benefits:** Higher Leverage from one prescription planner; fewer bugs hidden in orchestration; clearer Seam between deterministic planning, Agent review, and remote mutation; better alignment with Routine feedback/backfill ADR language.

2. **Separate result-sync safety policy from direct cascade mutation**
   - **Files:** `fitness_tracker/sync/_service.py` lines 161-175; `fitness_tracker/sync/hevy_true_coach/sync.py` lines 40-140; `fitness_tracker/sync_review/hevy_to_true_coach_result.py` lines 73-220; `fitness_tracker/sync_review/hevy_to_true_coach_result_planner.py` lines 22-131; `docs/adr/0006-hevy-to-truecoach-result-sync-uses-review-artifacts.md` lines 1-8.
   - **Problem:** Hevy updates automatically cascade into direct True Coach mutation, while ADR 0006 says brittle result mappings should use review/apply artifacts. The review planner has explicit candidates, blockers, omissions, partial apply, and completion status. The legacy path has repair logic and direct PUTs, but little Locality for mapping decisions.
   - **Deletion test:** Deleting the legacy result syncer would break the automatic cascade, but not the review/apply capability. Deleting the review path would lose the documented safety model. This suggests the Seam is policy, not API access.
   - **Solution sketch:** Deepen a result-sync workflow boundary that can choose direct apply only when the planner has no blockers and policy allows automation; otherwise emit review artifacts. Preserve the legacy refresh/repair behavior as a reusable Implementation detail rather than owning the mapping policy.
   - **Benefits:** Keeps performed-result semantics from `CONTEXT.md` local to one workflow; reduces accidental completion of unresolved Workouts; improves testability by testing plan/apply policy instead of full API orchestration.

3. **Move review writer ports/adapters out of the ADR-rejected sync port layer**
   - **Files:** `docs/adr/0002-sync-layer-uses-concrete-wiring.md` lines 1-15; `fitness_tracker/sync/ports/hevy_workout_writer.py` lines 1-49; `fitness_tracker/sync/adapters/hevy_workout_writer.py` lines 1-64; `fitness_tracker/sync_review/true_coach_to_hevy.py` lines 146-158; `fitness_tracker/sync_review/hevy_to_true_coach_result.py` lines 172-220.
   - **Problem:** `sync/ports` says “sync layer ports” even though ADR 0002 says that architecture was reverted. Some writer Interfaces are now useful to review/apply workflows, but their location leaks an old architecture into new Modules. The Adapters are mostly shallow pass-throughs, so the naming adds conceptual cost without much Depth.
   - **Deletion test:** Deleting `sync/ports` entirely breaks live review imports and checkpoint typing, so ADR completion is blocked by misplaced live seams. Deleting individual pass-through Adapters would often just require calling concrete API clients, except where the Adapter has real workflow logic like remote idempotency lookup.
   - **Solution sketch:** Keep only seams with real workflow Leverage, colocated with the workflow that needs them. Leave checkpoint storage with `SyncService`, and either inline shallow writers or move review-specific mutation seams under `sync_review`/workflow apply Modules.
   - **Benefits:** Aligns code with ADR 0002; improves Locality of mutation boundaries; removes misleading shallow Modules; makes future agents less likely to reintroduce broad ports/adapters.

4. **Deepen the Split Circuit workflow Adapter concept**
   - **Files:** `docs/adr/0007-split-circuit-planning-uses-shared-review-core.md` lines 1-22; `fitness_tracker/sync_review/routine_prescription.py` lines 317-428; `fitness_tracker/sync_review/workout_backfill_performed_work.py` lines 295-420; `fitness_tracker/sync_review/workout_backfill_request.py` lines 143-180.
   - **Problem:** The shared core exists, but the workflow Adapter logic is embedded inside large Modules. Routine creation and Workout backfill each resolve templates, convert set rows, allocate/group supersets, render notes, and build blockers in separate places. Backfill also derives requestability and blockers later from dicts, so a concept like “performed split-circuit movement with decision state” is spread across multiple Modules.
   - **Deletion test:** Deleting `split_circuit/core.py` would break both workflows, confirming it is deep. Deleting the embedded adapter code is impossible without touching many unrelated concerns in 858-line and 888-line Modules, showing weak Locality at the Adapter seam.
   - **Solution sketch:** Extract the workflow-specific split-circuit adaptation out of the large planners into narrow Modules that translate core plans into Routine blocks or backfill performed items. Keep the core free of concrete Hevy request objects as ADR 0007 requires.
   - **Benefits:** Better Leverage for new circuit behaviors; clearer boundaries between prescription parsing, performed evidence, and Hevy request adaptation; easier tests around omissions/replacements/rest/grouping without full planner setup.

5. **Give review artifacts a typed internal shape before JSON serialization**
   - **Files:** `fitness_tracker/sync_review/true_coach_to_hevy.py` lines 160-191 and 241-283; `fitness_tracker/sync_review/workout_backfill_request.py` lines 103-205; `fitness_tracker/sync_review/hevy_to_true_coach_result_planner.py` lines 66-81.
   - **Problem:** Many Modules pass `dict[str, Any]` plans through build/validate/apply stages. The JSON artifact is a good external Interface, but internally the same dict keys become a hard-to-test implicit Interface. Bugs can hide when orchestration changes a key, because request builders and blockers are string-key consumers far away from the planner.
   - **Deletion test:** If `plan.json` serialization were removed from an in-memory apply path, much of the business logic should still work. Today `write_apply_request()` reads back the just-written JSON (`true_coach_to_hevy.py` lines 135-139), proving the artifact format is acting as an internal Interface.
   - **Solution sketch:** Keep JSON artifacts as the external audit trail, but use typed plan/value objects inside planners, validators, and request builders, serializing at the workflow boundary.
   - **Benefits:** Stronger Locality for plan fields; easier refactors; better tests for orchestration without filesystem round-trips; fewer shallow helper functions that only protect dict access.

6. **Split the CLI into command Modules around workflow seams**
   - **Files:** `fitness_tracker/cli.py` lines 90-172, 438-610, 1769-1928; line count check shows `fitness_tracker/cli.py` is 2547 lines.
   - **Problem:** The CLI is a large shallow Module that knows every command, parser option, service construction, dry-run/apply branch, manual request path, output text, and some domain patching (`_write_patched_truecoach_to_hevy_request`). It has low Depth: lots of pass-through and branch plumbing, but any new workflow change touches the same file.
   - **Deletion test:** Deleting the CLI should not delete domain capability, but today it would remove nontrivial apply variants and patching behavior, meaning workflow logic leaked across the CLI Seam.
   - **Solution sketch:** Move command families into Modules that align with deep workflow boundaries (`sync_review`, `sync_apply`, `hevy maintenance`, etc.). Keep top-level CLI as a dispatcher.
   - **Benefits:** Better Locality for command changes; less merge friction; clearer boundary between user Interface and workflow Implementation; lower risk of bugs hidden in argparse/orchestration branches.
