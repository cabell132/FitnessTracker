# Split Circuit planning uses shared review core with workflow adapters

Routine creation and Workout backfill both need the same prescription-side
Split Circuit plan for Circuit blocks and multi-exercise AMRAP blocks, so the
shared planning logic belongs in `fitness_tracker/sync_review/split_circuit/core.py`.
Routine creation and Workout backfill should adapt that shared plan through
workflow-specific modules rather than duplicating Circuit parsing, exercise
target interpretation, template resolution, rest metadata, and grouping rules.

The shared core is deliberately scoped to Routine creation and Workout backfill;
Result sync review is out of scope. The Split Circuit plan carries generated
exercises, template resolution status, rest metadata, round/count evidence,
review blockers, and Circuit grouping intent, but not concrete Hevy request
objects or numeric Hevy `superset_id` values. Athlete-history enrichment remains
outside the Split Circuit plan and is applied only by Routine creation after the
plan is adapted.

Workout backfill may add performed evidence to the shared prescription plan, but
the backfilled Hevy Workout must contain only performed work. Clearly omitted
exercises may remain in review evidence, but they must not be emitted into the
backfilled Hevy Workout or persisted as synthetic tracker Workout Items; named
replacement exercises require an explicit Agent decision.
